import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export async function serverApi<T>(path: string): Promise<T> {
  const jar = await cookies();
  const response = await fetch(
    `${process.env.INTERNAL_API_URL || "http://localhost:8000"}/api/v1${path}`,
    { cache: "no-store", headers: { Cookie: jar.toString() } },
  );
  if (response.status === 401) redirect("/login");
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(
      payload.error?.message ||
        "The workspace service is unavailable. Please retry.",
    );
  }
  return response.json();
}
