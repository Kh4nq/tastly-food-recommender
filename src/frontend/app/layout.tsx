import type { Metadata } from "next";
import Header from "@/components/layout/Header";
import { Geist, Geist_Mono } from "next/font/google";
import TopNoiceBar from "@/components/layout/TopNoiceBar";

import "./globals.css";
import Footer from "@/components/layout/Footer";
import { getLang, getT } from "@/lib/i18n-server";
import { getLocation } from "@/lib/location-server";
import ChatWidget from "../components/chat/ChatWidget";
import { LangProvider } from "@/components/layout/LangProvider";
import { SearchLocationProvider } from "@/components/location/SearchLocationProvider";
import { SearchPreferenceProvider } from "@/components/search/SearchPreferenceProvider";

// Google fonts exposed as CSS variables (used by Tailwind)
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Page title/description follow the current language
export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return {
    title: t.meta.title,
    description: t.meta.description,
  };
}

// Shared shell for every page: header, notice bar, page content, footer
export default async function RootLayout({ children }: LayoutProps<"/">) {
  const lang = await getLang();
  const { selected } = await getLocation();

  return (
    <html
      lang={lang}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Gives client components access to the current language */}
        <LangProvider lang={lang}>
          <SearchLocationProvider initialLocation={selected}>
            <SearchPreferenceProvider>
            <Header />
            <TopNoiceBar />
            {children}
            <Footer />
            <ChatWidget />
            </SearchPreferenceProvider>
          </SearchLocationProvider>
        </LangProvider>
      </body>
    </html>
  );
}
