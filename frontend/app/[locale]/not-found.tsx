import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  const t = useTranslations("notFound");
  return (
    <main className="container-qp section-pad text-center">
      <p className="figure text-6xl text-lightgray" aria-hidden="true">
        404
      </p>
      <h1 className="title-md mt-6">{t("title")}</h1>
      <p className="mt-3 text-dim">{t("description")}</p>
      <Button asChild className="mt-8">
        <Link href="/">{t("backHome")}</Link>
      </Button>
    </main>
  );
}
