import Image from "next/image";

type SpecialtyCardProps = {
  image: string;
  name: string;
  region: string;
};

// Card for one regional specialty: photo, name and region
export default function SpecialtyCard({ image, name, region }: SpecialtyCardProps) {
  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm">
      <div className="relative h-48 bg-neutral-100">
        <Image
          src={image}
          alt={name}
          fill
          sizes="(min-width: 1024px) 25vw, (min-width: 640px) 50vw, 100vw"
          className="object-cover"
        />
      </div>
      <div className="p-3">
        <h3 className="font-semibold text-ink">{name}</h3>
        <p className="text-sm text-neutral-500">{region}</p>
      </div>
    </div>
  );
}