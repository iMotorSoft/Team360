# Laboratorio de pruebas tecnicas

Crear un directorio `lab/` para experimentos pequenos, reproducibles y aislados de produccion.

## Objetivo

Usar `lab/` para probar hipotesis tecnicas sin tocar flujos productivos directamente.

Cada prueba debe poder ejecutarse desde la raiz del proyecto, dejar evidencia auditable y producir una conclusion clara.

`lab/` no es codigo temporal descartable. Es un banco de pruebas reproducible para decidir rapido sin reconstruir todo el contexto.

## Casos de uso en Team360

`lab/` puede usarse para:

* comparar modelos LLM;
* comparar embeddings;
* medir latencia, costo, calidad y tasa de error;
* probar prompts de diagnostico;
* probar estrategias de chunking;
* comparar respuestas contra golden answers;
* validar paquetes knowledge antes de produccion;
* probar integracion con proveedores externos en entorno aislado;
* generar infografias HTML para revision tecnica o ejecutiva.

## Estructura recomendada

```text
lab/
  nombre-del-experimento/
    README.md
    run_experiment.py
    scripts/
      compare_results.py
      generate_infographics.py
    results/
      20260609_nombre_run.json
      20260609_nombre_run.md
    infografias/
      index.html
      01_resultados.html
      02_costos.html
      03_comparacion.html
    golden_answers/
      caso_prueba_golden.json
```

## Reglas

* Cada experimento vive en su propia carpeta dentro de `lab/`.
* El experimento debe ser autocontenido: scripts, README, comandos y resultados en el mismo directorio.
* No modificar configuracion productiva desde `lab/`.
* No escribir en bases, colecciones, buckets o servicios productivos salvo que el experimento lo declare explicitamente y use un entorno aislado.
* Guardar siempre resultados en formatos auditables:
  * JSON para datos completos.
  * Markdown para resumen humano.
  * HTML para revision visual o presentacion ejecutiva.
* Los archivos generados deben incluir timestamp en el nombre cuando corresponda.
* Mantener nombres exactos de modelos, servicios, versiones o dependencias probadas.
* No borrar resultados historicos utiles; sirven como baseline.

## README de cada experimento

El `README.md` de cada experimento debe explicar:

* que se esta probando;
* por que importa;
* como ejecutarlo;
* que dependencias necesita;
* que entorno usa;
* si toca servicios externos;
* que resultado se considera OK;
* conclusion de runs validados;
* decision tomada: adoptar, descartar, repetir con cambios o mantener como benchmark.

## Patron de ejecucion

Cada prueba deberia seguir este flujo:

1. Ejecutar script principal del experimento.
2. Guardar salida cruda en `results/*.json`.
3. Generar resumen en `results/*.md`.
4. Si aplica, comparar contra baseline o golden answer.
5. Generar infografia HTML estatica en `infografias/`.
6. Documentar conclusion en el `README.md`.

## Convencion de comandos

Los comandos se ejecutan siempre desde la raiz del proyecto.

Ejemplo generico:

```bash
python lab/nombre-del-experimento/run_experiment.py
python lab/nombre-del-experimento/scripts/compare_results.py
python lab/nombre-del-experimento/scripts/generate_infographics.py
```

Si el proyecto usa un gestor especifico, respetarlo.

Con entorno virtual:

```bash
.venv/bin/python lab/nombre-del-experimento/run_experiment.py
```

Con Poetry:

```bash
poetry run python lab/nombre-del-experimento/run_experiment.py
```

Con uv:

```bash
uv run python lab/nombre-del-experimento/run_experiment.py
```

En Team360, preferir `uv run` cuando el modulo o subproyecto ya este usando `uv`.

## Criterio de calidad

Una prueba de `lab/` se considera bien cerrada si deja:

* script reproducible;
* entrada o configuracion explicita;
* resultado JSON;
* resumen Markdown;
* infografia HTML cuando aporte claridad;
* conclusion practica;
* proximos pasos o decision: adoptar, descartar, repetir con cambios o mantener como benchmark.

## Buenas practicas

* Preferir scripts pequenos y directos antes que frameworks complejos.
* Separar medicion de presentacion: un script mide, otro genera infografias.
* Incluir costos, latencia, errores, tasa de exito y riesgos si aplica.
* Mantener nombres exactos de modelos, servicios, versiones o dependencias probadas.
* No borrar resultados historicos utiles; sirven como baseline.
* Si una prueba depende de servicios externos, documentar fecha, proveedor, modelo/version y configuracion usada.
* Si una prueba se adopta, migrarla luego a codigo productivo, tests o documentacion formal segun corresponda.

## Relacion con produccion

`lab/` no reemplaza tests productivos.

Los experimentos aprobados deben transformarse luego en una de estas salidas:

* codigo productivo;
* test automatizado;
* documentacion tecnica;
* benchmark conservado;
* decision explicita de descarte.

`lab/` permite experimentar sin contaminar flujos productivos, pero no debe convertirse en una segunda implementacion paralela del sistema.
