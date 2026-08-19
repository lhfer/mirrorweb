import "./style.css";
import { App } from "./app/App";
import { installQAHooks } from "./debug/QAHooks";

const app = new App();
await app.start();
installQAHooks(app);
