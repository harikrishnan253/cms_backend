import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useLocation } from "react-router-dom";

export function ComingSoonPage() {
  const location = useLocation();
  const pageName = location.pathname.replace("/", "").replace(/-/g, " ");
  useDocumentTitle(`${pageName} — S4Carlisle CMS`);

  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-12">
      <div className="w-16 h-16 bg-amber-50 rounded-full flex items-center justify-center mb-4">
        <svg className="w-8 h-8 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-slate-800 mb-2 capitalize">{pageName}</h2>
      <p className="text-slate-500 text-sm">This section is coming soon.</p>
    </div>
  );
}
