"use client";

// /admin is just an entry point people type or bookmark - it has no content
// of its own. It deliberately does NOT redirect here: the admin layout
// already owns every routing decision for this section (send to /admin/login
// when there's no valid session, otherwise to /admin/catalog). Having both
// this page and the layout call router.replace() raced them against each
// other and crashed with "Rendered more hooks than during the previous
// render", so routing lives in exactly one place.
//
// This renders the same spinner the layout shows while it checks the
// session, so the hand-off is seamless.
export default function AdminIndexPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-brand-500" />
    </div>
  );
}
