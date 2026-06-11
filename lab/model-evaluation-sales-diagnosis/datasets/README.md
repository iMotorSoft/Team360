# Datasets

Este directorio puede contener copias locales del dataset de evaluacion o enlaces al original.

El dataset canónico se encuentra en:

```
SrvRestAstroLS_v1/backend/tests/fixtures/sales_diagnosis_headless_questions_v1.json
```

Para usar el dataset canónico desde el lab, usar una de estas opciones:

1. Enlace simbólico:
   ```bash
   ln -s ../../SrvRestAstroLS_v1/backend/tests/fixtures/sales_diagnosis_headless_questions_v1.json \
     lab/model-evaluation-sales-diagnosis/datasets/sales_diagnosis_headless_questions_v1.json
   ```

2. Ruta absoluta en `run_matrix.json`:
   ```json
   {
     "dataset_path": "/abs/path/to/SrvRestAstroLS_v1/backend/tests/fixtures/sales_diagnosis_headless_questions_v1.json"
   }
   ```

3. Copia local (si se requiere versionar experimentos):
   ```bash
   cp SrvRestAstroLS_v1/backend/tests/fixtures/sales_diagnosis_headless_questions_v1.json \
     lab/model-evaluation-sales-diagnosis/datasets/
   ```

No duplicar el dataset canónico salvo que el experimento requiera una versión modificada.