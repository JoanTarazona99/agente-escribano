import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);

// Arrancar el servidor antes de todos los tests
beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));

// Resetear handlers entre tests para evitar contaminación
afterEach(() => server.resetHandlers());

// Cerrar el servidor tras todos los tests
afterAll(() => server.close());
