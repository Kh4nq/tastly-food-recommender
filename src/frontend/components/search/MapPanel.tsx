"use client";
import dynamic from "next/dynamic";

const MapPanel = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-neutral-100" />,
});

export default MapPanel;
