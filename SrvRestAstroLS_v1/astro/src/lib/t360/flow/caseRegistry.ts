// Team360 Flow — registro de casos conocidos para el Directorio.
//
// El backend Flow no expone todavía un endpoint de LISTADO de casos
// (GET /api/team360-flow/executive/{request_id} es solo por caso). Mientras
// exista ese gap, el Directorio consulta la vista ejecutiva real de cada
// request_id de este registro. Cada ID proviene de `flow_requests` reales
// (PostgreSQL), NO es fabricado: los hechos mostrados salen del backend.
//
// Gap identificado (documentado en el gate): el Directorio solo puede listar
// casos conocidos; cuando el backend ofrezca listado, este registro debe
// reemplazarse por la respuesta del endpoint.

export const FLOW_KNOWN_CASE_IDS: readonly string[] = [
  "9285797d-4939-4732-a28a-68c50df6bb77",
  "5b158027-7a2f-4c24-8c0e-1394846d3898",
  "4b6208e7-a3f7-4e85-a3d2-6560934cc974",
  "abbac03b-781c-4268-baa4-2cf58c11b27a",
  "ae90c03b-2c13-4975-ba98-12bed02d8514",
  "d8ea4604-9fb2-40a3-94e3-0a9f8b57c678",
  "333a15d0-b3cd-4ec1-ba01-b0a9593f087f",
  "22168509-3dc5-4834-8c7a-652f555bcc87",
  "a690c502-7729-41d4-b6b0-d3823bbf78d8",
  "c92d739c-4e6e-4b84-a65d-99a6a90ef712",
  "814f38ce-9509-4cd6-a355-fa176e63edb2",
  "d16a0a08-315b-47a8-9790-aaece91bde5f",
  "b0265a36-abca-4e2b-a0f3-1c9437446cb0",
  "56076a27-4927-495c-b3f6-1a4fe309f31e",
  "2ff06dc7-719f-45cf-a08a-177e4e9d77a8",
  "7b8fd0cf-7645-448a-97b7-217aceacaf08",
  "28f8e055-ac93-4c02-9e16-9bc98871fd39",
  "60aefb18-3f68-445f-8ba0-b7c0dc98e53f",
  "12f3ca08-7055-4b89-baba-2ff4bf91e5b1",
  "bd764a44-5a15-46ea-ae6c-0816f7047cc8",
  "43024969-2b8e-42df-8887-0f1982e7976b",
  "c5dac3b9-a1a2-49ad-9632-e33db84c2416",
  "818126f6-84ad-4c40-bbef-480ccfc0387b",
  "656977af-cc29-43d6-b78c-53464818f06a",
];

export function describeCaseRegistry(): { count: number; note: string } {
  return {
    count: FLOW_KNOWN_CASE_IDS.length,
    note: "Registro de casos conocidos: el backend aún no expone listado.",
  };
}
