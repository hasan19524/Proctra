import { redirect } from "next/navigation";

/** The bare /room demo route is gone — meets now live at /room/{code}. */
export default function LegacyRoomPage() {
  redirect("/");
}
