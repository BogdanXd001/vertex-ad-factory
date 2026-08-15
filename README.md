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

## Automatizare din ComfyUI

Panoul web pornește în fundal un job complet pentru toate etapele configurate,
fără comenzi repetate pentru fiecare scenă. Voice-over-ul este cerut o singură
dată de la ElevenLabs, cu timpi pe caractere, apoi este tăiat automat pentru
toate scenele. Cadrele sunt ordonate pe familii de modele — toate scenele
`flux_pulid`, apoi toate scenele `flux_base` — fără cerere de eliberare a
modelelor între ele. Raportul `runs/JOB_ID/performance.json` păstrează timpii
cold/warm și accelerarea măsurată.

Activarea panoului se face o singură dată:

```bash
ad-factory install-dashboard --comfy-root /workspace/ComfyUI --restart
```

După restart, deschide `/vertex-ad-factory/` pe aceeași adresă pe care folosești
ComfyUI, salvează ElevenLabs API key și Voice ID, apoi apasă **Pornește
automatizarea**. Cheia este salvată doar local, într-un fișier cu permisiuni
`0600`, și nu este returnată de API.

În versiunea curentă, runnerul finalizează voice-over-ul și toate first
frame-urile, apoi intră explicit în `waiting_input`. Pentru continuarea automată
cu image-to-video, lip-sync și asamblare este necesar exportul API al
workflow-urilor ComfyUI care funcționează deja pe instanța GPU; sistemul nu
inventează noduri sau modele incompatibile.

## Verificare locală

```bash
ad-factory init-db
ad-factory comfy-health
```

## Blueprint hibrid expert-podcast

Blueprint-ul pilot combină aproximativ 30% A-roll cu specialistă și 70% B-roll
educațional. Scenele on-camera sunt marcate pentru lip-sync, iar animațiile,
compositing-ul produsului și end card-ul sunt rutate separat.

```bash
ad-factory validate-blueprint blueprints/oceaura_expert_podcast_30s.json
ad-factory create-from-blueprint blueprints/oceaura_expert_podcast_30s.json
```

Comanda de creare nu modifică joburile existente. Ea creează un job nou, cu
toate cele șapte scene și metadatele de producție salvate în SQLite.

## Dry-run pentru primul cadru A-roll

Comanda modifică o copie a workflow-ului și nu trimite nimic către GPU.
Dimensiunea implicită este 720 × 1280, adică 9:16 exact.

```bash
ad-factory render-first-frame \
  --prompt "Photorealistic Moldovan skin-care specialist in a white coat, speaking in a premium podcast studio" \
  --seed 42
```

## Primul test GPU controlat

O scenă trebuie înregistrată înainte de generare. Comanda de submit așteaptă
rezultatul, îl salvează în SQLite și nu regenerează scena la o reluare decât
dacă primește `--force`.

```bash
ad-factory submit-first-frame JOB_ID \
  --position 1 \
  --reference-image A1_contradiction.png \
  --seed 42
```
