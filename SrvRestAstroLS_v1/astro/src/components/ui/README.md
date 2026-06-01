# Team360 UI Primitives

Wrappers visuales propios de Team360. Las pantallas de negocio deben consumir estos componentes y no dispersar clases DaisyUI.

Fase 1 incluye primitives suficientes para validar el stack: `Alert`, `Badge`, `Button`, `Card` y `Loading`.

La home publica agrega `LinkButton.astro` como wrapper semantico para CTAs enlazables.

Las pantallas mock concretas de consola agregan `EmptyState`, `SectionHeader`, `StatCard`, `StatusBadge` y `Tabs`. Estos wrappers concentran jerarquia visual, estados, copy legible y tabs reutilizables sin convertir DaisyUI en contrato de dominio.

Pendientes para fases siguientes: `Modal`, `Drawer`, `DataTable`, `FormField`, `TextInput`, `Select` y `Textarea`.
