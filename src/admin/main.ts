import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./styles.css";
import { AdminApp } from "./app";
import { LocalAdminAdapter } from "./adapters/local";
import { hasSupabaseEnvironment, SupabaseAdminAdapter } from "./adapters/supabase";

const root = document.querySelector<HTMLElement>("#admin-root");
if (!root) throw new Error("Missing #admin-root");

const adapter = hasSupabaseEnvironment()
  ? new SupabaseAdminAdapter()
  : new LocalAdminAdapter();

const app = new AdminApp(root, adapter);
void app.start();

if (import.meta.hot) {
  import.meta.hot.dispose(() => app.destroy());
}
