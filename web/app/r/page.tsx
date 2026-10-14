import { Suspense } from "react";
import ReportView from "./ReportView";

/* useSearchParams needs a Suspense boundary to prerender as a static page. */
export default function ReportPage() {
  return (
    <Suspense fallback={null}>
      <ReportView />
    </Suspense>
  );
}
