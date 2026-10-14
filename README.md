# Smartly AI — AI Video Transcription & Analysis

Pipeline permettant de récupérer une vidéo (URL ou fichier local), d'en extraire et transcrire
l'audio, d'identifier les différents locuteurs, puis de produire une analyse structurée
(résumé, points clés, sujets) à l'aide d'un LLM.

## Sommaire

- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Choix techniques](#choix-techniques)
- [Installation](#installation)
- [Utilisation de l'API](#utilisation-de-lapi)
- [Format de sortie](#format-de-sortie)
- [Exemples de résultats](#exemples-de-résultats)
- [Gestion des erreurs et robustesse](#gestion-des-erreurs-et-robustesse)
- [Tests effectués](#tests-effectués)
- [Tests automatisés](#tests-automatisés)
- [Limites connues](#limites-connues)
- [Fonctionnalités complémentaires](#fonctionnalités-complémentaires)
- [Pistes d'amélioration](#pistes-damélioration)

---

## Architecture

```
Vidéo (URL ou upload)
        │
        ▼
  Ingestion (yt-dlp / upload direct)
        │
        ▼
  Extraction audio (ffmpeg → WAV mono 16kHz PCM16)
        │
        ▼
   ┌─────────────────────┴─────────────────────┐
   ▼                                            ▼
Transcription (faster-whisper)          Diarisation (pyannote.audio)
   │                                            │
   └─────────────────────┬─────────────────────┘
                          ▼
        Alignement transcription ↔ locuteurs (recouvrement temporel)
        │
        ▼
  Persistance des segments (PostgreSQL)
        │
        ▼
  Analyse LLM par chunks (Ollama) ──► résumés partiels
        │
        ▼
  Synthèse globale (Ollama) ──► summary / key_points / topics
        │
        ▼
  Résultat final structuré
```

Le traitement est asynchrone : la requête `POST /videos/analyze-video` retourne
immédiatement un `job_id`, pendant que le pipeline s'exécute en tâche de fond
(`BackgroundTasks`). Le client peut suivre la progression en interrogeant
`GET /videos/{video_id}/status`, qui expose l'étape en cours (`current_stage`)
et le statut du job (`pending` → `running` → `completed` / `failed`).
> **Note performance** : les étapes de transcription et de diarisation sont indépendantes
> (toutes deux ne dépendent que de l'audio prétraité) et sont donc exécutées **en parallèle**
> via un `ThreadPoolExecutor`, plutôt que séquentiellement. `faster-whisper` (ctranslate2) et
> `pyannote.audio` (torch) libèrent le GIL Python pendant leur calcul natif, ce qui permet un
> vrai gain de temps sur les machines multi-cœurs, y compris en environnement CPU-only.

### Métadonnées récupérées à l'ingestion

Dès l'étape d'ingestion, le système extrait et persiste les principales métadonnées de la
vidéo, quelle que soit sa source (URL ou fichier local) : **titre**, **durée** exacte (en
secondes), **description** associée (lorsqu'elle est disponible sur la source d'origine), et
**source** du contenu (`url` ou `upload`). Ces informations sont visibles dès le dashboard,
avant même la fin du traitement complet du pipeline, et sont conservées en base aux côtés du
résultat de l'analyse.

## Stack technique

| Composant | Technologie | Justification |
|---|---|---|
| API | FastAPI + SQLAlchemy | Async natif, validation Pydantic, écosystème Python cohérent avec les modèles ML utilisés |
| Base de données | PostgreSQL 16 | Persistance des vidéos, jobs, segments et résultats |
| Ingestion vidéo | `yt-dlp` | Support large de plateformes vidéo, léger, pas de GPU requis |
| Extraction audio | `ffmpeg` | Standard, fiable, contrôle fin du format de sortie |
| Speech-to-Text | `faster-whisper` (modèle `base`, quantifié `int8`) | Voir [Choix techniques](#choix-techniques) |
| Speaker Diarization | `pyannote.audio` (`speaker-diarization-3.1`) | Détection de locuteurs sans supposer leur nombre à l'avance |
| Analyse | Ollama (LLM local, ex. `llama3.2:3b`) | Pas de dépendance à une API payante, exécutable sur CPU |
| Frontend | React + TypeScript + Vite | SPA légère consommant l'API REST |

## Choix techniques

### Speech-to-Text : faster-whisper

- **Choix du modèle** : `faster-whisper` en taille `base`, `compute_type=int8`, exécuté sur CPU.
  C'est une réimplémentation CTranslate2 de Whisper, nettement plus rapide et moins gourmande
  en mémoire que l'implémentation officielle OpenAI, tout en gardant une qualité de
  transcription équivalente.
- **Avantages** : rapide sur CPU, supporte nativement la détection automatique de langue,
  filtrage VAD intégré (`vad_filter=True`) pour ignorer les silences, timestamps par segment.
- **Limites** : les modèles `base`/`small` sont moins précis que `large-v3` sur de l'audio
  bruité, du vocabulaire technique, ou des accents marqués. Ce compromis entre vitesse et précision permet d'exécuter le pipeline sur CPU, sans nécessiter de GPU dédié.
- **Traitements appliqués** : voir la section preprocessing ci-dessous.

### Preprocessing audio

Avant transcription, la piste audio est extraite et normalisée via `ffmpeg` :
- conversion en WAV,
- **mono** (`-ac 1`) : la diarisation et la transcription n'ont pas besoin du stéréo, et cela
  réduit la taille des fichiers,
- **16 kHz** (`-ar 16000`) : fréquence d'échantillonnage attendue par Whisper et par le modèle
  de diarisation pyannote, évite un rééchantillonnage interne redondant,
- **PCM 16-bit signé** (`pcm_s16le`) : format non compressé, garantissant une qualité stable
  en entrée des modèles.

Le système accepte tout format vidéo lisible par `ffmpeg` (MP4, MOV, WEBM, AVI, MKV, etc.) —
aucune restriction d'extension n'est appliquée côté serveur, seule la capacité de `ffmpeg` à
décoder le fichier détermine la compatibilité. L'interface suggère MP4/MOV/WEBM comme formats
courants, mais ce n'est qu'une indication, pas une limite technique.
Cette étape échoue explicitement (`AudioExtractionError`) si le fichier vidéo est introuvable,
si `ffmpeg` retourne une erreur, ou si le fichier audio produit est vide — évitant de
transmettre un fichier corrompu aux étapes suivantes.

### Speaker Diarization

- **Approche** : `pyannote/speaker-diarization-3.1`, exécuté sur l'audio prétraité (mono,
  16kHz). Le modèle ne reçoit aucune indication a priori sur le nombre de locuteurs — il les détecte lui-même, sans connaissance préalable du nombre de personnes qui interviennent.
- **Association transcription ↔ locuteurs** : chaque segment de transcription Whisper est
  comparé à l'ensemble des segments de diarisation ; on lui attribue le locuteur dont le
  segment **recouvre le plus dans le temps** (overlap maximal entre `[start, end]` des deux
  sources). Si aucun recouvrement n'est trouvé, le locuteur reste `null` plutôt que d'être
  deviné.
- **`number_of_speakers`** : calculé comme le nombre de labels de locuteurs **distincts**
  réellement détectés par pyannote — jamais déduit ou estimé par le LLM.
- **Limite connue** : la diarisation est non bloquante par choix (voir Robustesse) — si elle
  échoue (ex. `HF_TOKEN` manquant/invalide, modèle indisponible), le pipeline continue avec
  une transcription non attribuée plutôt que d'échouer entièrement.

### Stratégie pour les contenus longs

La transcription n'est jamais envoyée en un seul bloc au LLM. Elle est découpée en chunks de
`N` segments (`ANALYSIS_CHUNK_SIZE`, configurable, 10 par défaut) :

```
Segments transcrits
        │
        ▼
Découpage en chunks de N segments
        │
        ▼
Analyse indépendante de chaque chunk (résumé + points + sujets partiels)
        │
        ▼
Agrégation : dédoublonnage des résumés/points/sujets
        │
        ▼
Synthèse finale par le LLM à partir des résultats agrégés
```

Cette approche conserve un temps de réponse et une consommation mémoire stables (le prompt
ne grandit pas linéairement avec la durée de la vidéo), et permet de traiter des vidéos plus
longues que la fenêtre de contexte du modèle utilisé.

### Modèle LLM

Utilisation d'**Ollama** en local (par défaut `llama3.2:3b`, configurable via
`OLLAMA_MODEL`), choisi pour :
- fonctionner sans GPU dans un environnement contraint (type Colab CPU),
- éviter toute dépendance à une API externe payante,
- offrir un temps de réponse acceptable sur un modèle de petite taille par rapport à des
  modèles 7B+, trop lents en environnement CPU pur.

Le prompt impose une sortie JSON stricte (`format: "json"`) avec des règles explicites
interdisant l'invention d'information ("N'invente aucune information").

## Installation

### Prérequis

- Docker et Docker Compose
- Un fichier `.env` à la racine (voir `.env.example`)

### Variables d'environnement principales

```env
APP_NAME=Smartly AI
APP_ENV=development
APP_VERSION=0.1.0

POSTGRES_DB=smartly_ai
POSTGRES_USER=smartly
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
BACKEND_PORT=8000

OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b
ANALYSIS_CHUNK_SIZE=10
OLLAMA_TIMEOUT=600

HF_TOKEN=hf_xxx        # requis pour pyannote (modèle gated sur HuggingFace)

STORAGE_PATH=/app/storage
MAX_UPLOAD_SIZE_MB=500
```

> `HF_TOKEN` : un compte HuggingFace gratuit + acceptation des conditions d'utilisation du
> modèle `pyannote/speaker-diarization-3.1` sont nécessaires pour générer un token valide.

### Démarrage

```bash
# 1. Build et lancement des conteneurs
docker compose up --build -d

# 2. Téléchargement du modèle LLM (une seule fois)
docker compose exec ollama ollama pull llama3.2:3b

# 3. Application des migrations de base de données
docker compose exec backend alembic upgrade head

# 4. Vérification
curl http://localhost:8000/health
```

L'API est ensuite documentée et testable via Swagger UI : `http://localhost:8000/docs`

Le frontend (si lancé séparément en dev) :

```bash
cd frontend
npm install
npm run dev
```

## Utilisation de l'API

### Analyser une vidéo depuis une URL

```bash
curl -X POST http://localhost:8000/videos/analyze-video \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/video"}'
```

Réponse :
```json
{
  "video": { "id": 1, "source_type": "url", "title": "...", "status": "pending", ... },
  "job_id": 7
}
```

### Analyser un fichier vidéo local

```bash
curl -X POST http://localhost:8000/videos/analyze-video/upload \
  -F "file=@/chemin/vers/video.mp4"
```

### Suivre la progression

```bash
curl http://localhost:8000/videos/1/status
```

```json
{
  "id": 7,
  "video_id": 1,
  "status": "running",
  "current_stage": "transcription",
  "error_message": null,
  "created_at": "...",
  "started_at": "...",
  "completed_at": null
}
```

Étapes possibles de `current_stage` : `audio_extraction` → `transcription` → `diarization`
→ `saving_transcript` → `ai_analysis` → `saving_analysis` → `completed` (ou `error`).

### Récupérer le résultat complet

```bash
curl http://localhost:8000/videos/1/result
```

## Format de sortie

```json
{
  "title": "Interview AI",
  "duration": 850,
  "number_of_speakers": 2,
  "transcript": [
    {
      "start": 0.5,
      "end": 5.8,
      "speaker": "SPEAKER_01",
      "text": "Bienvenue dans cette nouvelle émission."
    },
    {
      "start": 6.1,
      "end": 11.4,
      "speaker": "SPEAKER_02",
      "text": "Merci pour votre invitation."
    }
  ],
  "summary": "Cette vidéo présente...",
  "key_points": [
    "Présentation du projet",
    "Discussion sur l'IA générative",
    "Prochaines étapes"
  ],
  "topics": ["Artificial Intelligence", "LLM", "Cloud"]
}
```

### Statistiques globales (dashboard)

```bash
curl http://localhost:8000/videos/stats
```

```json
{
  "total_videos": 19,
  "completed": 10,
  "failed": 6,
  "processing": 3,
  "avg_processing_seconds": 4516.2,
  "total_duration_seconds": 1871.5,
  "avg_speakers": 1.9,
  "recent": [ /* 5 dernières analyses */ ]
}
```

Utilisé par le tableau de bord du frontend pour donner une vue d'ensemble : nombre
d'analyses par statut, temps de traitement moyen, volume total de contenu traité, nombre
moyen de locuteurs détectés, et activité récente.

### Exporter les sous-titres (.srt)

```bash
curl http://localhost:8000/videos/1/subtitles.srt -o sous-titres.srt
```

Génère un fichier `.srt` standard (SubRip) à partir du transcript, directement compatible
avec VLC, YouTube, et la plupart des lecteurs vidéo. Chaque bloc de sous-titre inclut le
label du locuteur lorsqu'il est disponible (ex. `SPEAKER_01: Bonjour.`). Renvoie une erreur
404 si la transcription n'est pas encore disponible, ou 422 si tous les segments sont vides.


## Exemples de résultats

Extraits réels obtenus via `GET /videos/{id}/result`, illustrant les différents cas testés
(voir aussi la section [Tests effectués](#tests-effectués)). Les transcriptions longues sont
tronquées ici pour la lisibilité — les résultats complets sont exportables en JSON depuis
l'interface.

### Un seul locuteur — qualité audio correcte (`qualite-correcte.mp4`)

```json
{
  "title": "qualite-correcte.mp4",
  "duration": 120.5,
  "number_of_speakers": 1,
  "transcript": [
    {
      "start": 0,
      "end": 7.8,
      "speaker": "SPEAKER_00",
      "text": "Dans cette vidéo, je vais te montrer comment tu vas créer ton podcast professionnel que tu le fasses chez toi au bien dans un local ou autre."
    },
    {
      "start": 7.8,
      "end": 14,
      "speaker": "SPEAKER_00",
      "text": "Je vais te montrer toutes les étapes techniques de A-AZ, de comment on va faire pour créer son podcast professionnel."
    }
    // ... 27 segments supplémentaires (transcript complet dans l'export JSON)
  ],
  "summary": "Le présentateur expose les étapes techniques nécessaires pour créer un podcast professionnel, en commençant par la recherche d'un espace adapté et en choisissant des éléments décoratifs qui correspondent à son branding.",
  "key_points": [
    "Rechercher un espace adapté",
    "Choisir un arrière-plan et une lumière appropriés",
    "Acheter une table de décoration",
    "Choisir des couleurs pour la table",
    "Sélectionner des sièges confortables",
    "Avoir des verres de couleurs"
  ],
  "topics": [
    "Étapes techniques pour créer un podcast professionnel",
    "Choix du lieu et des éléments décoratifs"
  ]
}
```

### Plusieurs locuteurs avec bruit de fond (`bruit-fond.mp4`)

6 intervenants réels, 5 locuteurs distincts détectés (voir commentaire dans
[Tests effectués](#tests-effectués)) :

```json
{
  "title": "bruit-fond.mp4",
  "number_of_speakers": 5,
  "transcript": [
    {
      "start": 0.11,
      "end": 5.81,
      "speaker": "SPEAKER_04",
      "text": "Bonjour à tous, l'intelligence artificielle occupent de plus en plus de place dans notre société et continue d'animer les débats."
    },
    {
      "start": 12.11,
      "end": 20.79,
      "speaker": "SPEAKER_03",
      "text": "Pas trop, non."
    }
    // ... 165 segments supplémentaires (transcript complet dans l'export JSON)
  ],
  "summary": "L'intelligence artificielle occupe une place croissante dans notre vie quotidienne, posant des questions sur sa présence et ses avantages. Il est important de traiter ce sujet avec prudence et régulation pour éviter les risques potentiels.",
  "key_points": [
    "L'intelligence artificielle est un sujet de débat actuel",
    "L'IA peut être bénéfique, mais elle fait peur à cause de la substitution de certains métiers",
    "Il faut que ce sujet soit traité par des professionnels avant que les sociétés privées s'en emparent",
    "Il est important de réguler les sociétés privées pour éviter leur libre développement",
    "L'intelligence artificielle peut être complémentaire si dosée correctement"
  ],
  "topics": [
    "L'intelligence artificielle dans la société",
    "Sécurité et technologie",
    "Régulation des sociétés privées et intervention étatique"
  ]
}
```

### Plusieurs locuteurs — qualité propre (interview Sommet de la Francophonie)

```json
{
  "title": "multi-locuteurs.mp4",
  "number_of_speakers": 2,
  "transcript": [
    {
      "start": 0.21,
      "end": 5.37,
      "speaker": "SPEAKER_01",
      "text": "Et pour parler de ce sommet de la francophonie, de l'avenir de la langue française, Florence Teste enseignante en français, longue étrangère à l'EUF Université de Montpellier..."
    },
    {
      "start": 27.41,
      "end": 32.33,
      "speaker": "SPEAKER_00",
      "text": "Oui, c'est ça, je suis professeur de français, de l'angue étrangère depuis, effectivement, très longtemps..."
    }
    // ... segments supplémentaires (transcript complet dans l'export JSON)
  ],
  "summary": "Florence Teste, professeur de français depuis plus de 40 ans, raconte son expérience en tant qu'enseignante. La langue française est une passion qui lui permet de se sentir valorisée à l'étranger. Le sommet de la francophonie est important pour elle, car il rassemble les gens derrière des valeurs et un point commun universel.",
  "key_points": [
    "Florence Teste enseigne le français depuis plus de 40 ans",
    "Elle aime son métier pour rencontrer des personnes de cultures différentes",
    "La langue française est une passion qui lui permet de se sentir valorisée à l'étranger",
    "Le sommet de la francophonie rassemble les gens derrière des valeurs communes",
    "L'enseignement en Asie a été une expérience marquante de son parcours professionnel"
  ],
  "topics": [
    "L'avenir de la langue française",
    "L'importance du métier d'enseignant en français langue étrangère",
    "La francophonie",
    "L'enseignement en Asie"
  ]
}
```

### Multilingue — espagnol (`Easy Spanish Conversation Podcast`)

Vidéo soumise par URL, langue détectée et transcrite automatiquement sans configuration
manuelle (voir [Bonus implémentés](#bonus-implémentés)) :

```json
{
  "title": "Easy Spanish Conversation Podcast",
  "description": "Learn Spanish with this Easy Podcast for Beginners! \n\nDo you understand this text?",
  "duration": 66,
  "number_of_speakers": 1,
  "transcript": [
    {
      "start": 0,
      "end": 4.08,
      "speaker": "SPEAKER_00",
      "text": "Hola, me llamo a mira y bienvenido a este podcast."
    },
    {
      "start": 4.08,
      "end": 8.24,
      "speaker": "SPEAKER_00",
      "text": "Soy de Egipto y vivo en España desde hace cuatro años."
    }
    // ... segments supplémentaires (transcript complet dans l'export JSON)
  ],
  "summary": "L'émetteur présente sa réussite dans la maîtrise de l'espagnol après quatre années d'apprentissage, puis invite les auditeurs à essayer eux-mêmes.",
  "key_points": [
    "Le présentateur a commencé par utiliser des applications et des cours pour apprendre la langue",
    "Il avait peur de parler espagnol à son arrivée en Espagne",
    "L'auditeur peut lui aussi apprendre la langue avec la même détermination"
  ],
  "topics": [
    "Apprentissage d'une langue étrangère et détermination personnelle"
  ]
}
```

### Multilingue — arabe (`اسأل نفسك! 🤍`)

```json
{
  "title": "اسأل نفسك! 🤍 - احسان بنعلوش",
  "duration": 23,
  "number_of_speakers": 1,
  "transcript": [
    { "start": 0, "end": 2, "speaker": "SPEAKER_00", "text": "لا تسأل آخرين عنك" },
    { "start": 2, "end": 4, "speaker": "SPEAKER_00", "text": "ولا عن مستقبل كل عن أهدافك" },
    { "start": 4, "end": 6, "speaker": "SPEAKER_00", "text": "لا إسأل نفسكم الأعماء" }
    // ... 10 segments supplémentaires (transcript complet dans l'export JSON)
  ],
  "summary": "L'intervenant rappelle l'importance de ne pas demander à d'autres pour connaître soi-même et son avenir. Il partage son expérience selon laquelle les autres peuvent ne pas avoir de réponses, mais que cela n'affecte pas le fait qu'il ait trouvé ce qu'il cherchait.",
  "key_points": [
    "Ne pas demander à d'autres pour se connaître soi-même",
    "L'avenir n'est pas prévisible et les autres peuvent ne pas avoir de réponses",
    "La recherche personnelle est essentielle"
  ],
  "topics": [
    "Autonomie et recherche personnelle",
    "L'imprévisibilité du futur"
  ]
}
```


## Gestion des erreurs et robustesse

| Cas d'échec | Comportement |
|---|---|
| URL invalide / vidéo indisponible | `VideoIngestionError` → HTTP 400 avec message explicite, aucune entrée créée en base |
| Audio inexploitable | `AudioExtractionError`, job marqué `failed` avec `error_message` détaillé |
| Absence de parole détectée | La transcription lève une erreur explicite plutôt que de renvoyer un résultat vide silencieux |
| Échec du modèle de transcription | Exception propagée jusqu'au pipeline, job marqué `failed` |
| Échec de la diarisation | **Non bloquant** : le pipeline continue avec des locuteurs non attribués (`speaker: null`) plutôt que d'échouer entièrement |
| Échec de l'analyse LLM (timeout, JSON invalide) | Exception capturée, job marqué `failed`, aucun résultat inventé n'est retourné |
| Exception imprévue en tâche de fond | Capturée et journalisée (`logging`) dans `_run_analysis_background` — n'interrompt jamais le processus principal de l'API |

**Principe directeur** : à aucun moment le système ne retourne un résultat partiel présenté
comme complet, ni une information devinée pour masquer un échec (ex. nombre de locuteurs,
transcription vide). En cas d'échec, `AnalysisJob.status = "failed"` et `error_message`
contient la cause, consultable via `GET /videos/{video_id}/status`.

## Tests effectués

| Type de vidéo | Résultat | Commentaire |
|---|---|---|
| Un seul locuteur | ✅ testé — `number_of_speakers: 1` | Vidéo d'entretien d'embauche simulé où une seule personne interprète les deux rôles (recruteur et candidat). La diarisation détecte correctement une unique voix physique malgré un contenu textuel simulant un dialogue à deux, confirmant que la détection se base sur les caractéristiques vocales réelles et non sur la structure du texte. |
| Plusieurs locuteurs | ✅ testé — `number_of_speakers: 2` | Interview de 5:38 (Sommet de la Francophonie) avec une journaliste et une invitée. La diarisation détecte correctement les 2 locuteurs distincts et les segments de transcription leur sont bien attribués individuellement (`SPEAKER_00`/`SPEAKER_01`), confirmant le bon fonctionnement de l'alignement transcription ↔ diarisation sur un cas réel à 2 voix. |
| Bruit de fond | ✅ testé — 5/6 locuteurs détectés | Vidéo avec musique/bruit de fond en continu et 6 intervenants réels (`bruit-fond.mp4`) : la diarisation détecte 5 locuteurs distincts sur 170 segments. Résultat globalement satisfaisant malgré le bruit — un léger sous-comptage (5 au lieu de 6) plutôt qu'une sur-segmentation, cohérent avec le fait que `pyannote` regroupe parfois deux locuteurs aux caractéristiques vocales proches ou aux temps de parole très courts dans un même cluster. Le bruit dégrade aussi légèrement la transcription elle-même, ce qui se répercute sur l'analyse LLM en aval (le résumé généré contient une légère hallucination lexicale, probablement due à un passage mal transcrit). |
| Qualité audio correcte | ✅ testé — `number_of_speakers: 1` | Vidéo `qualite-correcte.mp4` (podcast tutoriel sur la création de podcast, audio propre, un seul intervenant) : 29 segments, diarisation cohérente (`SPEAKER_00` unique), transcription fidèle et résumé/points clés cohérents avec le contenu. Confirme que la précision du pipeline (transcription + diarisation + analyse LLM) est bonne dans des conditions audio favorables, par contraste avec le cas du bruit de fond ci-dessus. |
| Absence de parole (clip musical chanté) | ✅ testé — `status: failed` | Le système détecte correctement l'absence de parole exploitable via le VAD intégré à `faster-whisper` et retourne `error_message: "No speech detected in the audio."` au lieu de produire un résultat vide ou inventé, ce qui garantit une gestion explicite des cas où aucune parole exploitable n'est détectée. |

## Tests automatisés

Le projet inclut une suite de tests unitaires (`pytest`) couvrant la logique métier
critique, indépendamment des modèles ML lourds (mockés) :

```bash
cd backend
pytest tests/ -v
```

| Fichier | Couverture |
|---|---|
| `test_video_service.py` | Téléchargement vidéo (`yt-dlp`) : succès, échecs réseau, nettoyage des fichiers partiels, fichier manquant après téléchargement |
| `test_alignment_service.py` | Association transcription ↔ locuteurs : overlap simple, overlap maximal entre plusieurs locuteurs, absence de recouvrement, diarisation vide, segments multiples |
| `test_schemas.py` | Validation des schémas Pydantic (`VideoURLRequest`) |
| `test_analysis_pipeline.py` | Orchestration complète du pipeline : succès, diarisation non bloquante en cas d'échec, transcription bloquante en cas d'échec, job/vidéo introuvables |
| `test_srt_service.py` | Génération SRT : format des timestamps, labels de locuteurs, segments vides ignorés, transcript vide, numérotation séquentielle |
| `test_video_routes.py` | Endpoints HTTP (`TestClient`) : codes de statut, gestion des erreurs 400/404/422, contrat de réponse de chaque route |

Les tests de routes (`test_video_routes.py`) mockent explicitement l'exécution de la tâche
de fond (`_run_analysis_background`) pour ne tester que le contrat HTTP de l'API, sans
déclencher le chargement réel des modèles ML (Whisper, pyannote) — cette logique métier est
déjà couverte indépendamment par `test_analysis_pipeline.py`. Cette séparation permet de
garder la suite de tests rapide (quelques secondes) tout en couvrant les deux niveaux
(orchestration pipeline + contrat API).

Les modèles ML (`faster-whisper`, `pyannote.audio`, Ollama) sont mockés dans les tests
unitaires pour ne pas dépendre de leur téléchargement/exécution réelle en CI.

## Limites connues

- Le téléchargement via `yt-dlp` peut être bloqué par certaines plateformes (ex. YouTube
  retourne parfois une erreur 403 selon l'IP source, les quotas ou des mesures anti-bot) — le
  système gère ce cas proprement (erreur 400 explicite) mais ne peut pas le contourner.
- Le modèle Whisper `base` et le LLM léger (`llama3.2:3b`) offrent un compromis
  vitesse/précision adapté aux contraintes CPU, mais restent moins précis que des modèles plus
  lourds sur de l'audio difficile (bruit important, accents forts, chevauchement de paroles).
- **La précision de la transcription varie selon la langue source.** Les tests réalisés en
  français et en espagnol donnent une transcription fidèle, mais le test en arabe
  (`اسأل نفسك`) montre une dégradation notable de la qualité — mots mal reconnus ou
  substitués (ex. structures répétées mal transcrites) alors que le contenu audio est propre
  et sans bruit de fond. Ce comportement est cohérent avec le fait que le modèle `base` de
  Whisper est entraîné sur un corpus majoritairement anglophone/européen, et donc
  significativement moins performant sur l'arabe que sur les langues latines à taille de
  modèle égale. Un modèle Whisper plus grand (`small`/`medium`) améliorerait probablement ce
  point, au prix d'un temps de traitement plus élevé en environnement CPU-only.
- La diarisation peut manquer de précision sur de courts tours de parole successifs ou des
  locuteurs à la voix très similaire.
- **L'analyse LLM (résumé/points clés/sujets) est produite en français, quelle que soit la
  langue de la vidéo source.** Une expérimentation a été menée pour rendre la langue de sortie
  configurable (auto-détection via `info.language`, avec possibilité de forcer une langue via
  l'API) : le branchement technique fonctionnait bout en bout (langue bien transmise et
  persistée jusqu'au prompt), mais `llama3.2:3b` s'est montré incapable de suivre une consigne
  de langue de sortie explicite lorsque le reste du prompt système est rédigé en français —
  même avec l'instruction répétée en tête et en fin de prompt. Un modèle plus grand
  (`qwen2.5:7b`) suit correctement ce type de consigne, mais au prix d'une latence
  significativement plus élevée en environnement CPU-only, ce qui a motivé le choix de revenir
  à une sortie français-only pour cette version, plutôt que de dégrader le temps de traitement
  global. Cette expérimentation met en évidence le compromis entre la taille du modèle, la fiabilité des résultats et les ressources matérielles disponibles.
- Le traitement est actuellement synchrone au sein du `BackgroundTask` (un seul job à la fois
  par processus) — pas encore de file d'attente distribuée (Celery/RQ) pour la montée en
  charge. En revanche, au sein d'un même job, transcription et diarisation sont parallélisées
  (voir Architecture) pour réduire le temps de traitement par vidéo.

- **Contrainte matérielle de test** : développé et testé sur un CPU mobile bas de gamme
  (Intel i5-6300U, 2 cœurs physiques / 4 threads logiques, 16 Go RAM), donnant une vitesse de
  génération LLM d'environ 1.5-2 tokens/seconde avec Ollama — ce qui peut faire dépasser le
  timeout par défaut sur des vidéos longues avec beaucoup de chunks. Le partage des ressources
  CPU entre l'OS hôte et Docker/WSL2 a été volontairement laissé à sa configuration par défaut
  (aucune allocation dédiée forcée) pour ne pas dégrader l'utilisabilité de la machine pendant
  le développement. Ce compromis a motivé les optimisations suivantes : plafonnement de la
  longueur de génération LLM (`num_predict`), augmentation de `ANALYSIS_CHUNK_SIZE` pour
  réduire le nombre d'appels séquentiels au LLM, et timeout Ollama dimensionné en conséquence
  (`OLLAMA_TIMEOUT`). Sur un CPU de bureau moderne ou dans un environnement dédié (type VM
  cloud, Google Colab), les temps de traitement seraient nettement réduits. Cette contrainte matérielle a conduit à privilégier des vidéos courtes pour les tests (environ 23 secondes à 6 minutes selon les cas, voir la section [Exemples de résultats](#exemples-de-résultats)). Le pipeline peut également traiter des vidéos plus longues, avec un temps de traitement qui augmente selon leur durée et leur complexité.

## Fonctionnalités complémentaires

- **Détection automatique de la langue** : `faster-whisper` détecte automatiquement la langue
  parlée (`info.language`, avec score de confiance `language_probability`) sans configuration
  préalable, permettant nativement la prise en charge de plusieurs langues.
- **Transcription multilingue évaluée** : le pipeline a été testé sur six langues — français, anglais, espagnol, allemand, arabe et chinois. Les résultats varient selon la langue et la qualité audio ; des améliorations restent notamment nécessaires pour la transcription en arabe.
- **Export sous-titres (.srt)** : le transcript timestampé peut être exporté au format `.srt`
  standard (`GET /videos/{id}/subtitles.srt`), directement utilisable comme piste de
  sous-titres dans n'importe quel lecteur vidéo (VLC, YouTube, etc.) — une fonctionnalité complémentaire permettant d'exploiter les transcriptions dans les lecteurs vidéo compatibles.
- **Interface utilisateur soignée** : dashboard avec statistiques globales et graphiques, page
  d'historique des analyses, et mode sombre.

## Pistes d'amélioration

- File d'attente de jobs (Celery/RQ + Redis) pour paralléliser plusieurs analyses.
- WebSocket pour pousser la progression en temps réel plutôt que du polling HTTP.
- Cache des modèles (Whisper/pyannote) préchargés au démarrage du conteneur plutôt qu'au
  premier appel, pour réduire la latence de la première requête.
- Transcription en temps réel (streaming) pour des cas d'usage live, en complément du
  traitement asynchrone actuel.
- Sélection dynamique de la taille du modèle STT (`tiny`/`base`/`small`/`large`) selon le
  compromis vitesse/précision souhaité.
- Notifications webhook à la fin du traitement, en alternative au polling `GET .../status`.
- Traitement par lot (batch) permettant de soumettre plusieurs vidéos en une seule requête.
- Fine-tuning ciblé du modèle STT sur l'arabe pour corriger la dégradation de qualité observée
  lors des tests.
