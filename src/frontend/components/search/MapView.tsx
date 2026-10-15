"use client";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo } from "react";
import type { Location } from "@/lib/api";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import MapboxView from "./MapboxView";

export type Place = {
  id: string;
  name: string;
  dish?: string;
  lat: number;
  lon: number;
  distance_km?: number | null;
  price_vnd?: number | null;
  priority?: boolean;
};

type MapViewProps = {
  places: Place[];
  userLocation?: Location;
  activeId: string | null; // highlighted place , shared with the list
  selectedId?: string | null;
  onClearSelection?: () => void;
  onSelect: (id: string) => void;
};

const DEFAULT_CENTER: [number, number] = [10.7769, 106.7009]; // HCM city
const DEFAULT_ZOOM = 13;
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = "&copy; OpenStreetMap";

const COLORS = { place: "#c0392b", user: "#2563eb", active: "#1f1b16" };

const pinIcon = (color: string) =>
  L.divIcon({
    className: "",
    html: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 36 44" width="36" height="44" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))">
      <path d="M16 0C7.16 0 0 7.16 0 16c0 11.2 16 24 16 24s16-12.8 16-24C32 7.16 24.84 0 16 0z" fill="${color}" stroke="#fff" stroke-width="2"/>
      <circle cx="16" cy="16" r="6" fill="#fff"/>
    </svg>`,
    iconSize: [36, 44],
    iconAnchor: [18, 42], //  the tip of the drop
    popupAnchor: [0, -40], // popup opens above the pin head
  });

const placePin = pinIcon(COLORS.place);
const activePin = pinIcon(COLORS.active);
const userPin = pinIcon(COLORS.user);

// Zoom the map so every place is visible
function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();

  useEffect(() => {
    const fit = () => {
      map.invalidateSize();
      if (points.length > 0) {
        map.fitBounds(points, { padding: [40, 40], maxZoom: 16 });
      }
    };

    // A hidden container (mobile tab) has no width so wait until it shows up
    const observer = new ResizeObserver(() => {
      if (map.getContainer().clientWidth > 0) fit();
    });
    observer.observe(map.getContainer());
    fit();

    return () => observer.disconnect();
  }, [map, points]);

  return null;
}

export default function MapView({
  places,
  userLocation,
  activeId,
  selectedId,
  onClearSelection,
  onSelect,
}: MapViewProps) {
  // Include the user so both the user and the places are on screen
  const points = useMemo(() => {
    // Frame the ranked places (the nearest ones) and the user so the map zooms to the user's area
    const ranked = places.filter((p) => p.priority);
    const all = ranked.map((p): [number, number] => [p.lat, p.lon]);

    if (userLocation) all.push([userLocation.lat, userLocation.lon]);

    // Nothing ranked and no user position : fall back to every place
    if (all.length === 0) places.forEach((p) => all.push([p.lat, p.lon]));

    return all;
  }, [places, userLocation]);

  const token = process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN;
  if (token) {
    return (
      <MapboxView
        places={places}
        userLocation={userLocation}
        activeId={activeId}
        selectedId={selectedId}
        onSelect={onSelect}
        onClearSelection={onClearSelection}
        token={token}
      />
    );
  }

  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      scrollWheelZoom={true}
      className="h-full w-full"
    >
      <TileLayer url={TILE_URL} attribution={ATTRIBUTION} />
      <FitBounds points={points} />

      {userLocation && (
        <Marker
          position={[userLocation.lat, userLocation.lon]}
          icon={userPin}
          interactive={false}
          zIndexOffset={-1000} //  staty below the places
        />
      )}

      {places.map((p) => {
        const active = p.id === activeId;
        return (
          <Marker
            key={p.id}
            position={[p.lat, p.lon]}
            icon={active ? activePin : placePin}
            zIndexOffset={active ? 1000 : 0}
            eventHandlers={{ click: () => onSelect(p.id) }}
          >
            <Popup>
              <strong>{p.name}</strong>
              {p.dish && <div>{p.dish}</div>}
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
