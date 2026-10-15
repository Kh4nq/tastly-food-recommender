"use client";

import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { useEffect, useRef } from "react";
import type { Location } from "@/lib/api";
import type { Place } from "./MapView";
import { useT } from "../layout/LangProvider";

type Props = {
  places: Place[];
  userLocation?: Location;
  activeId: string | null;
  selectedId?: string | null;
  onClearSelection?: () => void;
  onSelect: (id: string) => void;
  token: string;
};

function dataFor(places: Place[]): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: places.map((p) => ({
      type: "Feature", id: p.id,
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: { id: p.id, name: p.name, dish: p.dish ?? "", priority: p.priority ?? false },
    })),
  };
}

export default function MapboxView(props: Props) {
  const t = useT();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const latest = useRef(props);
  const updateRef = useRef<(() => void) | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const directionLabel = t.lang === "vi" ? "Chỉ đường" : "Directions";
  const labelRef = useRef(directionLabel);
  const textRef = useRef({ lang: t.lang, price: t.price });

  useEffect(() => {
    latest.current = props;
    labelRef.current = directionLabel;
    textRef.current = { lang: t.lang, price: t.price };
    updateRef.current?.();
  }, [props, directionLabel, t.lang, t.price]);

  useEffect(() => {
    if (!container.current) return;
    const map = new mapboxgl.Map({
      container: container.current,
      accessToken: props.token,
      style: "mapbox://styles/mapbox/streets-v12",
      center: [106.7009, 10.7769], zoom: 13,
      attributionControl: true,
      fadeDuration: 0,
    });
    mapRef.current = map;
    map.scrollZoom.enable();
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    let userMarker: mapboxgl.Marker | null = null;
    let previousPlaces: Place[] | null = null;
    let previousLocation: Location | undefined;
    let previousSelectedId: string | null | undefined;

    function closePopup() {
      const popup = popupRef.current;
      popupRef.current = null;
      popup?.remove();
    }

    function showPopup(place: Place) {
      const vi = textRef.current.lang === "vi";
      const content = document.createElement("div");
      content.className = "tastly-map-popup";
      const title = document.createElement("strong");
      title.textContent = place.name;
      content.append(title);
      for (const value of [
        `${vi ? "Món ăn" : "Dish"}: ${place.dish || (vi ? "Chưa có thông tin" : "Unavailable")}`,
        `${vi ? "Khoảng cách" : "Distance"}: ${place.distance_km != null ? `${place.distance_km.toFixed(1)} km` : (vi ? "Chưa có vị trí tìm kiếm" : "Search location unavailable")}`,
        `${vi ? "Giá" : "Price"}: ${place.price_vnd != null ? textRef.current.price(place.price_vnd) : (vi ? "Chưa có giá" : "Unavailable")}`,
      ]) {
        const line = document.createElement("p");
        line.textContent = value;
        content.append(line);
      }
      const directions = document.createElement("a");
      directions.textContent = labelRef.current;
      directions.href = `https://www.google.com/maps/dir/?api=1&destination=${place.lat},${place.lon}`;
      directions.target = "_blank";
      directions.rel = "noopener noreferrer";
      content.append(directions);
      closePopup();
      const popup = new mapboxgl.Popup({ offset: 40, maxWidth: "320px", closeButton: true, className: "tastly-place-popup" })
        .setLngLat([place.lon, place.lat]).setDOMContent(content).addTo(map);
      popupRef.current = popup;
      popup.on("close", () => {
        if (popupRef.current === popup) {
          popupRef.current = null;
          latest.current.onClearSelection?.();
        }
      });
    }

    function update() {
      if (!map.getSource("places")) return;
      const current = latest.current;
      if (previousPlaces !== current.places || previousLocation !== current.userLocation) {
        (map.getSource("places") as mapboxgl.GeoJSONSource).setData(dataFor(current.places));
        (map.getSource("priority-places") as mapboxgl.GeoJSONSource).setData(dataFor(current.places.filter((p) => p.priority)));
        closePopup();
        previousSelectedId = undefined;
        userMarker?.remove();
        userMarker = current.userLocation
          ? new mapboxgl.Marker({ color: "#2563eb" }).setLngLat([current.userLocation.lon, current.userLocation.lat]).addTo(map)
          : null;
        const bounds = new mapboxgl.LngLatBounds();
        const rankedPlaces = current.places.filter((p) => p.priority);
        (rankedPlaces.length ? rankedPlaces : current.places).forEach((p) => bounds.extend([p.lon, p.lat]));
        if (current.userLocation) bounds.extend([current.userLocation.lon, current.userLocation.lat]);
        if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 48, maxZoom: 16, duration: 0 });
        previousPlaces = current.places;
        previousLocation = current.userLocation;
      }
      for (const layer of ["place-logos", "priority-place-logos"]) {
        if (!map.getLayer(layer)) continue;
        map.setLayoutProperty(layer, "icon-size", [
          "case", ["==", ["get", "id"], current.activeId ?? ""], 1.28, 1.1,
        ]);
        map.setLayoutProperty(layer, "symbol-sort-key", [
          "case", ["==", ["get", "id"], current.activeId ?? ""], layer === "priority-place-logos" ? 1 : -1, 0,
        ]);
      }
      const selectedId = current.selectedId ?? null;
      if (selectedId !== previousSelectedId) {
        previousSelectedId = selectedId;
        const place = current.places.find((p) => p.id === selectedId);
        if (place) {
          map.easeTo({ center: [place.lon, place.lat], duration: 350 });
          showPopup(place);
        } else closePopup();
      }
    }

    map.on("load", () => {
      map.addSource("places", { type: "geojson", data: dataFor(latest.current.places) });
      map.addSource("priority-places", { type: "geojson", data: dataFor(latest.current.places.filter((p) => p.priority)), cluster: true, clusterRadius: 48, clusterMaxZoom: 17 });
      map.addLayer({ id: "priority-clusters", type: "circle", source: "priority-places", filter: ["has", "point_count"], paint: {
        "circle-color": "#ff6b35", "circle-radius": 23, "circle-stroke-width": 3, "circle-stroke-color": "#ffffff",
      } });
      map.addLayer({ id: "priority-count", type: "symbol", source: "priority-places", filter: ["has", "point_count"], layout: {
        "text-field": ["get", "point_count_abbreviated"], "text-size": 16,
        "text-font": ["DIN Offc Pro Bold", "Arial Unicode MS Bold"],
        "text-allow-overlap": true,
      }, paint: { "text-color": "#ffffff" } });
      map.loadImage("/logo.png", (error, image) => {
        if (error || !image || mapRef.current !== map) return;
        // Use the brand's pin symbol; the full wordmark is too wide for a map marker.
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 96;
        const context = canvas.getContext("2d");
        if (!context) return;
        let source: CanvasImageSource;
        if (image instanceof ImageData) {
          const sourceCanvas = document.createElement("canvas");
          sourceCanvas.width = image.width;
          sourceCanvas.height = image.height;
          const sourceContext = sourceCanvas.getContext("2d");
          if (!sourceContext) return;
          sourceContext.putImageData(image, 0, 0);
          source = sourceCanvas;
        } else {
          source = image;
        }
        context.drawImage(source, 0, 0, image.width * 0.22, image.height * 0.9, 14, 2, 68, 90);
        map.addImage("tastly-logo", context.getImageData(0, 0, 96, 96), { pixelRatio: 2 });
        map.addLayer({
          id: "place-logos", type: "symbol", source: "places",
          minzoom: 15,
          filter: ["==", ["get", "priority"], false],
          layout: { "icon-image": "tastly-logo", "icon-size": 1.1, "icon-anchor": "bottom", "icon-allow-overlap": false, "icon-ignore-placement": false },
        });
        // Cluster only the ranked restaurants so dense areas remain readable.
        map.addLayer({
          id: "priority-place-logos", type: "symbol", source: "priority-places",
          filter: ["!", ["has", "point_count"]],
          layout: { "icon-image": "tastly-logo", "icon-size": 1.1, "icon-anchor": "bottom", "icon-allow-overlap": true, "icon-ignore-placement": false },
        });
        update();
      });
      updateRef.current = update;
      update();
    });

    map.on("click", "priority-clusters", (event) => {
      const feature = event.features?.[0];
      if (!feature || feature.geometry.type !== "Point") return;
      const center = feature.geometry.coordinates as [number, number];
      (map.getSource("priority-places") as mapboxgl.GeoJSONSource).getClusterExpansionZoom(
        Number(feature.properties?.cluster_id), (error, zoom) => {
          if (!error && zoom != null && mapRef.current === map) map.easeTo({ center, zoom, duration: 450 });
        },
      );
    });

    map.on("click", ["priority-place-logos", "place-logos"], (event) => {
      const feature = event.features?.[0];
      if (!feature || feature.geometry.type !== "Point") return;
      const place = latest.current.places.find((p) => p.id === feature.properties?.id);
      if (!place) return;
      latest.current.onSelect(place.id);
    });
    for (const layer of ["place-logos", "priority-place-logos", "priority-clusters"]) {
      map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
    }
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      updateRef.current = null;
      closePopup();
      userMarker?.remove();
      mapRef.current = null;
      map.remove();
    };
  }, [props.token]);

  return <div ref={container} className="h-full w-full" />;
}
