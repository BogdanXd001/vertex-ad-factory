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

