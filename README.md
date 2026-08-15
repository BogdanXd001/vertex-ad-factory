# Vertex Ad Factory

Orchestrator local pentru reclame educaționale și UGC generate cu ComfyUI.

Pipeline-ul este organizat pe etape reluabile:

1. planning
2. voiceover
3. first_frames
4. image_to_video
5. lipsync
6. assembly

Fiecare reclamă și scenă este înregistrată în SQLite. Un eșec nu obligă
reluarea întregului proiect; procesarea poate continua de la ultima etapă
finalizată.

## Verificare locală

```bash
ad-factory init-db
ad-factory comfy-health
```

## Dry-run pentru primul cadru A-roll

Comanda modifică o copie a workflow-ului și nu trimite nimic către GPU:

```bash
ad-factory render-first-frame \
  --prompt "Photorealistic podcast presenter" \
  --seed 42
```

## Primul test GPU controlat

O scenă trebuie înregistrată înainte de generare. Comanda de submit așteaptă
rezultatul, îl salvează în SQLite și nu regenerează scena la o reluare decât
dacă primește `--force`.

```bash
ad-factory add-scene JOB_ID \
  --position 1 \
  --kind a_roll \
  --duration 6 \
  --narration "Textul rostit în scenă" \
  --visual-prompt "Photorealistic podcast presenter"

ad-factory submit-first-frame JOB_ID \
  --position 1 \
  --reference-image A1_contradiction.png \
  --seed 42
```
