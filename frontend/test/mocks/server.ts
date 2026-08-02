/* MSW node server — used in vitest. */

import { setupServer } from "msw/node";

import { handlers } from "./handlers";

export const server = setupServer(...handlers);
