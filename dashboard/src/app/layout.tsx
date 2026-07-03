import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/Shell";
import { BUSINESS } from "@/lib/config";
import { getAttention, getKpis } from "@/lib/mock/data";

export const metadata: Metadata = {
  title: `${BUSINESS.name} — Jarvis Command Center`,
  description:
    "Centre de commandement : KPI temps réel, emails, social, campagnes, automatisations, alertes sous budget d'attention.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Instantané serveur : même contrat que rempliront les vrais connecteurs.
  const kpis = getKpis();
  const attention = getAttention();

  return (
    <html lang="fr" className="h-full antialiased">
      <body className="min-h-full">
        <Shell kpis={kpis} attention={attention}>
          {children}
        </Shell>
      </body>
    </html>
  );
}
