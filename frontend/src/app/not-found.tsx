import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-6">
      <div className="text-center">
        <h1 className="text-7xl font-bold text-primary">404</h1>
        <h2 className="mt-2 text-2xl font-semibold">Page not found</h2>
        <p className="mt-2 text-muted-foreground">The page you are looking for does not exist.</p>
      </div>
      <Link
        href="/"
        className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Go home
      </Link>
    </div>
  );
}
