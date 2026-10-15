import HeroSection from "@/components/home/HeroSection";
import SpinSection from "@/components/spin/SpinSection";
import MoodSection from "@/components/mood/MoodSection";
import TodayRecommendations from "@/components/home/TodayRecommendations";
import CategoryChips from "@/components/home/CategoryChips";

// Home page: sections stacked from top to bottom
export default function HomePage() {
  return (
    <main className="flex-1 space-y-12 pb-12 sm:space-y-16 sm:pb-16 lg:space-y-20 lg:pb-20">
      <div className="space-y-4 pt-4 sm:space-y-5 sm:pt-5">
        <HeroSection />
        <CategoryChips />
        <TodayRecommendations />
      </div>
      <SpinSection />
      <MoodSection />
    </main>
  );
}
