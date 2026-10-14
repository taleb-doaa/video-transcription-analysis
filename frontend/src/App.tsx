import { useEffect, useMemo, useRef, useState } from "react";
import {
  Home,
  History,
  Link2,
  UploadCloud,
  FileVideo,
  X,
  Sparkles,
  Loader2,
  AlertCircle,
  ChevronLeft,
  Clock,
  Globe2,
  FileText,
  Tags,
  CheckCircle2,
  Download,
  MessageSquareText,
  BarChart3,
  Users,
  XCircle,
  Timer,
  Subtitles,
  Sun,
  Moon,
} from "lucide-react";
import "./App.css";
import smartlyLogo from "./assets/smartly_logo.png";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

const API_URL = import.meta.env.VITE_API_URL || "";
const SPEAKER_COLORS = ["#1a73e8", "#34a853", "#ea4335", "#fbbc04", "#9334e6", "#12b5cb"];




interface VideoData {
  id: number;
  source_type: string;
  source_url: string | null;
  title: string | null;
  description: string | null;
  duration: number | null;
  status: string;
  current_stage?: string;
}

interface TranscriptSegment {
  start: number;
  end: number;
  speaker: string;
  text: string;
}

interface Analysis {
  id: number;
  video_id: number;
  number_of_speakers: number | null;
  summary: string | null;
  key_points: string[] | null;
  topics: string[] | null;
  transcript?: TranscriptSegment[] | null;
}


interface HistoryItem {
  id: number;
  title: string | null;
  description: string | null;
  source_type: string;
  source_url: string | null;
  duration: number | null;
  status: string;
  created_at: string | null;
}

interface DashboardRecentItem {
  id: number;
  title: string | null;
  status: string;
  source_type: string;
  duration: number | null;
  created_at: string | null;
}

interface DashboardStats {
  total_videos: number;
  completed: number;
  failed: number;
  processing: number;
  avg_processing_seconds: number | null;
  total_duration_seconds: number;
  avg_speakers: number | null;
  recent: DashboardRecentItem[];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function stageLabel(stage?: string): string {
  const labels: Record<string, string> = {
    audio_extraction: "Extraction de l'audio...",
    transcription: "Transcription en cours...",
    diarization: "Identification des locuteurs...",
    saving_transcript: "Enregistrement de la transcription...",
    ai_analysis: "Analyse par l'IA en cours...",
    saving_analysis: "Finalisation...",
  };
  return stage ? labels[stage] || "Traitement en cours..." : "Initialisation...";
}


function speakerColor(speaker: string): string {
  const sum = speaker.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return SPEAKER_COLORS[sum % SPEAKER_COLORS.length];
}

function speakerLabel(speaker: string): string {
  const match = speaker.match(/(\d+)/);
  return match ? `S${match[1]}` : speaker.slice(0, 2).toUpperCase();
}


function formatDuration(totalSeconds: number): string {
  if (!totalSeconds) return "0min";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.round((totalSeconds % 3600) / 60);
  if (hours > 0) return `${hours}h${minutes.toString().padStart(2, "0")}`;
  return `${minutes}min`;
}

function formatProcessingTime(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}min ${remainingSeconds}s`;
}

function relativeDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "à l'instant";
  if (diffMin < 60) return `il y a ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `il y a ${diffH}h`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `il y a ${diffD}j`;
  return date.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

function App() {
  const [mode, setMode] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [localPreviewUrl, setLocalPreviewUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const [videoData, setVideoData] = useState<VideoData | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeSegment, setActiveSegment] = useState(-1);
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [showFullDescription, setShowFullDescription] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("smartly-theme") as "light" | "dark") || "light"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("smartly-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  const videoRef = useRef<HTMLVideoElement>(null);
  const segmentRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    return () => {
      if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    };
  }, [localPreviewUrl]);

  const handleFileSelect = (selected: File | null) => {
    if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    setFile(selected);
    setLocalPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  };

  const resetAll = () => {
    setVideoData(null);
    setAnalysis(null);
    setError("");
    setUrl("");
    handleFileSelect(null);
    setActiveSegment(-1);
    setShowHistory(false);
    setShowDashboard(false);
  };


  const pollStatus = (videoId: number) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/videos/${videoId}/status`);
        const statusData = await res.json();

        setVideoData((prev) =>
          prev ? { ...prev, status: statusData.status, current_stage: statusData.current_stage } : prev
        );

        if (statusData.status === "completed") {
          clearInterval(interval);
          const resultRes = await fetch(`${API_URL}/videos/${videoId}/result`);

          if (!resultRes.ok) {
            const errData = await resultRes.json().catch(() => null);
            setError(errData?.detail || "Impossible de récupérer le résultat de l'analyse.");
            return;
          }

          const resultData: Analysis = await resultRes.json();
          console.log("RESULT DATA:", resultData);
          setAnalysis(resultData);
        }

        if (statusData.status === "failed") {
          clearInterval(interval);
          setError(statusData.error_message || "L'analyse a échoué.");
        }
      } catch {
        clearInterval(interval);
        setError("Connexion perdue avec le serveur pendant le suivi de l'analyse.");
      }
    }, 3000);
  };


  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_URL}/videos/`);
      const data: HistoryItem[] = await res.json();
      setHistoryItems(data);
    } catch {
      setError("Impossible de charger l'historique.");
    } finally {
      setHistoryLoading(false);
    }
  };

  const openHistory = () => {
    setShowHistory(true);
    setShowDashboard(false);
    setVideoData(null);
    setAnalysis(null);
    setError("");
    loadHistory();
  };

  const loadDashboard = async () => {
    setDashboardLoading(true);
    setDashboardStats(null);
    try {
      const res = await fetch(`${API_URL}/videos/stats`);

      if (!res.ok) {
        setError(`Impossible de charger le tableau de bord (erreur ${res.status}).`);
        return;
      }

      const data: DashboardStats = await res.json();
      setDashboardStats(data);
    } catch {
      setError("Impossible de charger le tableau de bord.");
    } finally {
      setDashboardLoading(false);
    }
  };

  const openDashboard = () => {
    setShowDashboard(true);
    setShowHistory(false);
    setVideoData(null);
    setAnalysis(null);
    setError("");
    loadDashboard();
  };

  const openVideoFromHistory = async (item: HistoryItem) => {
    setShowHistory(false);
    setShowDashboard(false);
    setError("");
    setAnalysis(null);
    setVideoData({
      id: item.id,
      source_type: item.source_type,
      source_url: item.source_url,
      title: item.title,
      description: item.description,
      duration: item.duration,
      status: item.status,
    });

    if (item.status === "completed") {
      try {
        const resultRes = await fetch(`${API_URL}/videos/${item.id}/result`);
        if (resultRes.ok) {
          const resultData: Analysis = await resultRes.json();
          setAnalysis(resultData);
        }
      } catch {
        setError("Impossible de charger le résultat de cette vidéo.");
      }
    } else if (item.status === "running" || item.status === "pending") {
      pollStatus(item.id);
    }
  };

  const analyzeVideo = async () => {
    if (mode === "url" && !url.trim()) {
      setError("Veuillez entrer une URL de vidéo.");
      return;
    }
    if (mode === "file" && !file) {
      setError("Veuillez sélectionner un fichier vidéo.");
      return;
    }

    setLoading(true);
    setError("");
    setVideoData(null);
    setAnalysis(null);

    try {
      let response: Response;

      if (mode === "file" && file) {
        const formData = new FormData();
        formData.append("file", file);
        response = await fetch(`${API_URL}/videos/analyze-video/upload`, {
          method: "POST",
          body: formData,
        });
      } else {
        response = await fetch(`${API_URL}/videos/analyze-video`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url.trim() }),
        });
      }

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Impossible d'analyser cette vidéo.");
      }

      const data = await response.json();
      setVideoData(data.video);        
      pollStatus(data.video.id);       
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur inattendue est survenue.");
    } finally {
      setLoading(false);
    }
  };

  const handleTimeUpdate = () => {
    const segments = analysis?.transcript;
    const time = videoRef.current?.currentTime ?? 0;
    if (!segments) return;
    const idx = segments.findIndex((s) => time >= s.start && time < s.end);
    if (idx !== activeSegment) {
      setActiveSegment(idx);
      segmentRefs.current[idx]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  };

  const seekTo = (start: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = start;
      videoRef.current.play();
    }
  };

  const handleExport = () => {
    if (!videoData) return;
    const payload = { video: videoData, analysis };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = `${videoData.title || "analyse"}.json`;
    a.click();
    URL.revokeObjectURL(blobUrl);
  };

  const retryAnalysis = async (videoId: number) => {
    setError("");
    try {
      const response = await fetch(`${API_URL}/videos/${videoId}/retry`, {
        method: "POST",
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        setError(data?.detail || "Impossible de relancer cette analyse.");
        return;
      }

      const data = await response.json();
      setVideoData(data.video);
      setAnalysis(null);
      setShowHistory(false);
      setShowDashboard(false);
      pollStatus(data.video.id);
    } catch {
      setError("Connexion perdue lors de la relance de l'analyse.");
    }
  };

  const handleDownloadSubtitles = async () => {
    if (!videoData) return;
    try {
      const res = await fetch(`${API_URL}/videos/${videoData.id}/subtitles.srt`);
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        setError(errData?.detail || "Impossible de générer les sous-titres.");
        return;
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${videoData.title || "sous-titres"}.srt`;
      a.click();
      URL.revokeObjectURL(blobUrl);
    } catch {
      setError("Connexion perdue lors du téléchargement des sous-titres.");
    }
  };

  const previewSrc = localPreviewUrl || videoData?.source_url || null;
  const isPlayableSrc = useMemo(() => {
    if (localPreviewUrl) return true;
    if (!videoData?.source_url) return false;
    return /\.(mp4|webm|ogg|mov)(\?.*)?$/i.test(videoData.source_url);
  }, [localPreviewUrl, videoData]);

  const speakerCount =
    analysis?.number_of_speakers ??
    (analysis?.transcript ? new Set(analysis.transcript.map((s) => s.speaker)).size : null);

  return (
    <div className="shell">
      <aside className="sidebar">
        <a href="https://smartly.ai/" target="_blank" rel="noopener noreferrer" className="sidebar-logo">
          <img src={smartlyLogo} alt="Smartly AI" width={22} height={22} />
        </a>
        <nav className="sidebar-nav">
          <button
            className={`sidebar-btn${!showHistory && !showDashboard ? " active" : ""}`}
            onClick={resetAll}
            title="Nouvelle analyse"
          >
            <Home size={19} />
          </button>
          <button
            className={`sidebar-btn${showHistory ? " active" : ""}`}
            onClick={openHistory}
            title="Historique"
          >
            <History size={19} />
          </button>
          <button
            className={`sidebar-btn${showDashboard ? " active" : ""}`}
            onClick={openDashboard}
            title="Tableau de bord"
          >
            <BarChart3 size={19} />
          </button>
        </nav>
        <button
          className="sidebar-btn theme-toggle"
          onClick={toggleTheme}
          title={theme === "light" ? "Activer le mode sombre" : "Activer le mode clair"}
        >
          {theme === "light" ? <Moon size={19} /> : <Sun size={19} />}
        </button>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-left">
            {videoData || showHistory || showDashboard ? (
              <>
                <button className="back-btn" onClick={resetAll}>
                  <ChevronLeft size={16} />
                  Retour
                </button>
                <span className="topbar-divider" />
                <div className="topbar-title-group">
                  <span className="topbar-title">
                    {showDashboard
                      ? "Tableau de bord"
                      : showHistory
                      ? "Historique des analyses"
                      : videoData?.title || "Analyse en cours"}
                  </span>
                  {showHistory && (
                    <span className="topbar-sub">
                      {historyItems.length} vidéo{historyItems.length > 1 ? "s" : ""} analysée{historyItems.length > 1 ? "s" : ""}
                    </span>
                  )}
                  {showDashboard && (
                    <span className="topbar-sub">Vue d'ensemble de vos analyses</span>
                  )}
                </div>
              </>
            ) : (
              <span className="topbar-title">Smartly AI — Video Transcription & Analysis</span>
            )}
          </div>
        </header>

        <div className="content">
          {showDashboard && (
            <div className="dashboard-wrap">
              {dashboardLoading ? (
                <div className="transcript-loading">
                  <Loader2 size={22} className="spin" />
                  <p>Chargement du tableau de bord...</p>
                </div>
              ) : dashboardStats ? (
                <>
                  <div className="stats-grid">
                    <div className="stat-card">
                      <div className="stat-icon blue"><FileVideo size={18} /></div>
                      <div className="stat-info">
                        <span className="stat-value">{dashboardStats.total_videos}</span>
                        <span className="stat-label">Analyses totales</span>
                      </div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-icon green"><CheckCircle2 size={18} /></div>
                      <div className="stat-info">
                        <span className="stat-value">{dashboardStats.completed}</span>
                        <span className="stat-label">Terminées</span>
                      </div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-icon red"><XCircle size={18} /></div>
                      <div className="stat-info">
                        <span className="stat-value">{dashboardStats.failed}</span>
                        <span className="stat-label">Échouées</span>
                      </div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-icon yellow"><Loader2 size={18} /></div>
                      <div className="stat-info">
                        <span className="stat-value">{dashboardStats.processing}</span>
                        <span className="stat-label">En cours</span>
                      </div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-icon blue"><Timer size={18} /></div>
                      <div className="stat-info">
                        <span className="stat-value">
                          {formatProcessingTime(dashboardStats.avg_processing_seconds)}
                        </span>
                        <span className="stat-label">Temps moyen / vidéo</span>
                      </div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-icon blue"><Clock size={18} /></div>
                      <div className="stat-info">
                        <span className="stat-value">
                          {formatDuration(dashboardStats.total_duration_seconds)}
                        </span>
                        <span className="stat-label">Contenu traité</span>
                      </div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-icon blue"><Users size={18} /></div>
                      <div className="stat-info">
                        <span className="stat-value">{dashboardStats.avg_speakers ?? "—"}</span>
                        <span className="stat-label">Locuteurs / vidéo (moy.)</span>
                      </div>
                    </div>
                  </div>

                  {(dashboardStats.completed + dashboardStats.failed + dashboardStats.processing) > 0 && (
                    <div className="charts-grid">
                      <div className="chart-card">
                        <h4 className="chart-title">Répartition des statuts</h4>
                        <ResponsiveContainer width="100%" height={220}>
                          <PieChart>
                            <Pie
                              data={[
                                { name: "Terminées", value: dashboardStats.completed, color: "#34a853" },
                                { name: "Échouées", value: dashboardStats.failed, color: "#ea4335" },
                                { name: "En cours", value: dashboardStats.processing, color: "#fbbc04" },
                              ].filter((d) => d.value > 0)}
                              dataKey="value"
                              nameKey="name"
                              innerRadius={55}
                              outerRadius={80}
                              paddingAngle={3}
                            >
                              {[
                                { name: "Terminées", value: dashboardStats.completed, color: "#34a853" },
                                { name: "Échouées", value: dashboardStats.failed, color: "#ea4335" },
                                { name: "En cours", value: dashboardStats.processing, color: "#fbbc04" },
                              ]
                                .filter((d) => d.value > 0)
                                .map((entry) => (
                                  <Cell key={entry.name} fill={entry.color} />
                                ))}
                            </Pie>
                            <Tooltip />
                            <Legend verticalAlign="bottom" height={30} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>

                      <div className="chart-card">
                        <h4 className="chart-title">Durée des analyses récentes</h4>
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart
                            data={dashboardStats.recent.map((item) => ({
                              name: item.title
                                ? item.title.length > 14
                                  ? item.title.slice(0, 14) + "…"
                                  : item.title
                                : `#${item.id}`,
                              duree: item.duration ? Math.round(item.duration) : 0,
                            }))}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                            <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                            <YAxis tick={{ fontSize: 11 }} />
                            <Tooltip />
                            <Bar dataKey="duree" fill="#1a73e8" radius={[6, 6, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  <div className="dashboard-section-title">Activité récente</div>

                  {dashboardStats.recent.length ? (
                    <div className="history-table">
                      {dashboardStats.recent.map((item) => (
                        <div
                          key={item.id}
                          className="history-row history-item"
                          onClick={() => openVideoFromHistory({ ...item, source_url: null, description: null })}
                        >
                          <div className="history-item-title">
                            <div className="card-icon blue"><FileVideo size={16} /></div>
                            <strong>{item.title || `Vidéo #${item.id}`}</strong>
                          </div>
                          <span className="history-col hide-mobile">{item.source_type}</span>
                          <span className="history-col hide-mobile">
                            {item.duration ? `${Math.round(item.duration)}s` : "—"}
                          </span>
                          <span className="history-col hide-mobile">{relativeDate(item.created_at)}</span>
                          <span className={`status-pill ${item.status}`}>{item.status}</span>
                          <ChevronLeft size={16} className="history-chevron" style={{ transform: "rotate(180deg)" }} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="transcript-empty">
                      <BarChart3 size={26} />
                      <p>Aucune analyse pour le moment.</p>
                    </div>
                  )}
                </>
              ) : (
                <div className="transcript-empty">
                  <BarChart3 size={26} />
                  <p>Impossible de charger les statistiques.</p>
                </div>
              )}
            </div>
          )}

          {showHistory && (
            <div className="history-wrap">
              {historyLoading ? (
                <div className="transcript-loading">
                  <Loader2 size={22} className="spin" />
                  <p>Chargement de l'historique...</p>
                </div>
              ) : historyItems.length ? (
                <div className="history-table">
                  <div className="history-row history-head">
                    <span>Vidéo</span>
                    <span className="hide-mobile">Source</span>
                    <span className="hide-mobile">Durée</span>
                    <span className="hide-mobile">Date</span>
                    <span>Statut</span>
                    <span />
                  </div>
                  {historyItems.map((item) => (
                    <div
                      key={item.id}
                      className="history-row history-item"
                      onClick={() => openVideoFromHistory(item)}
                    >
                      <div className="history-item-title">
                        <div className="card-icon blue">
                          <FileVideo size={16} />
                        </div>
                        <strong>{item.title || `Vidéo #${item.id}`}</strong>
                      </div>
                      <span className="history-col hide-mobile">{item.source_type}</span>
                      <span className="history-col hide-mobile">
                        {item.duration ? `${Math.round(item.duration)}s` : "—"}
                      </span>
                      <span className="history-col hide-mobile">{relativeDate(item.created_at)}</span>
                      <span className={`status-pill ${item.status}`}>{item.status}</span>
                      <ChevronLeft size={16} className="history-chevron" style={{ transform: "rotate(180deg)" }} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="transcript-empty">
                  <BarChart3 size={26} />
                  <p>Aucune analyse pour le moment.</p>
                </div>
              )}
            </div>
          )}

          {!showHistory && !showDashboard && !videoData && (
            <div className="upload-wrap">
              <h2>Transcrivez et analysez n'importe quelle vidéo</h2>
              <p>Collez une URL publique ou glissez un fichier vidéo local.</p>

              <div className="upload-card">
                <div className="upload-tabs">
                  <button className={mode === "url" ? "active" : ""} onClick={() => setMode("url")}>
                    <Link2 size={14} /> URL
                  </button>
                  <button className={mode === "file" ? "active" : ""} onClick={() => setMode("file")}>
                    <FileVideo size={14} /> Fichier
                  </button>
                </div>

                {mode === "url" ? (
                  <div className="url-field">
                    <Link2 size={16} />
                    <input
                      type="url"
                      placeholder="https://www.youtube.com/watch?v=..."
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && analyzeVideo()}
                      disabled={loading}
                    />
                  </div>
                ) : file ? (
                  <div className="file-picked">
                    <div className="card-icon blue">
                      <FileVideo size={17} />
                    </div>
                    <div className="file-picked-info">
                      <strong>{file.name}</strong>
                      <span>{(file.size / (1024 * 1024)).toFixed(1)} Mo</span>
                    </div>
                    <button className="file-remove" onClick={() => handleFileSelect(null)}>
                      <X size={15} />
                    </button>
                  </div>
                ) : (
                  <label
                    className={`dropzone${dragOver ? " dragover" : ""}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOver(false);
                      const dropped = e.dataTransfer.files?.[0];
                      if (dropped) handleFileSelect(dropped);
                    }}
                  >
                    <UploadCloud size={26} />
                    <p>Glissez-déposez votre vidéo ici</p>
                    <span>ou cliquez pour parcourir — MP4, MOV, WEBM</span>
                    <input
                      type="file"
                      accept="video/*"
                      hidden
                      onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                    />
                  </label>
                )}

                <button className="analyze-btn" onClick={analyzeVideo} disabled={loading}>
                  {loading ? (
                    <>
                      <Loader2 size={16} className="spin" /> Analyse en cours...
                    </>
                  ) : (
                    <>
                      <Sparkles size={16} /> Analyser la vidéo
                    </>
                  )}
                </button>

                {error && (
                  <div className="error">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {!showHistory && !showDashboard && videoData && (
            <div className="result-grid">
              <div>
                <div className="card video-panel">
                  {isPlayableSrc && previewSrc ? (
                    <video ref={videoRef} src={previewSrc} controls onTimeUpdate={handleTimeUpdate} />
                  ) : (
                    <div className="video-fallback">
                      <FileVideo size={28} />
                      <strong>{videoData.title || "Vidéo source"}</strong>
                      <span>Aperçu non disponible pour cette source — voir les métadonnées ci-dessous.</span>
                    </div>
                  )}

                  <div className="video-meta">
                    <div className="video-meta-item">
                      <Clock size={14} />
                      <strong>{videoData.duration ? `${Math.round(videoData.duration)}s` : "—"}</strong>
                    </div>
                    <div className="video-meta-item">
                      <Globe2 size={14} />
                      <strong>{videoData.source_type}</strong>
                    </div>
                    <div className="video-meta-item">
                      <span className={`status-pill ${videoData.status}`} style={{ padding: "4px 10px" }}>
                        {videoData.status}
                      </span>
                    </div>
                  </div>

                  {videoData.description && (
                    <div className="video-description">
                      <p className={showFullDescription ? "" : "clamped"}>{videoData.description}</p>
                      {videoData.description.length > 200 && (
                        <button className="desc-toggle" onClick={() => setShowFullDescription((v) => !v)}>
                          {showFullDescription ? "Voir moins" : "Voir plus"}
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {analysis && (
                  <div className="card summary-card">
                    <h3>
                      <FileText size={16} /> Résumé analytique
                    </h3>
                    <p>{analysis.summary || "Aucun résumé disponible."}</p>

                    <div className="summary-block">
                      <h4>Points clés</h4>
                      <ul className="key-points">
                        {analysis.key_points?.length ? (
                          analysis.key_points.map((point) => (
                            <li key={point}>
                              <CheckCircle2 size={15} />
                              {point}
                            </li>
                          ))
                        ) : (
                          <li>Aucun point clé disponible.</li>
                        )}
                      </ul>
                    </div>

                    <div className="summary-block">
                      <h4>
                        <Tags size={12} style={{ marginRight: 4, verticalAlign: -2 }} />
                        Sujets
                      </h4>
                      <div className="tags">
                        {analysis.topics?.length ? (
                          analysis.topics.map((topic) => <span key={topic}>{topic}</span>)
                        ) : (
                          <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>Aucun sujet disponible.</p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="card transcript-panel">
                <div className="transcript-header">
                  <div className="transcript-header-top">
                    <h3>
                      <MessageSquareText size={15} style={{ marginRight: 6, verticalAlign: -2 }} />
                      Transcription
                    </h3>
                    {analysis?.transcript && <span className="status-pill">Terminé</span>}
                  </div>
                  <p className="transcript-sub">
                    {analysis?.transcript
                      ? `${analysis.transcript.length} segments${speakerCount ? ` · ${speakerCount} locuteur${speakerCount > 1 ? "s" : ""}` : ""}`
                      : "En attente de traitement"}
                  </p>
                </div>

                {analysis?.transcript?.length ? (
                  <div className="transcript-list">
                    {analysis.transcript.map((seg, i) => (
                      <div
                        key={`${seg.start}-${i}`}
                        ref={(el) => { segmentRefs.current[i] = el; }}
                        className={`segment${i === activeSegment ? " active" : ""}`}
                        onClick={() => seekTo(seg.start)}
                      >
                        <div className="segment-top">
                          <span className="speaker-chip" style={{ background: speakerColor(seg.speaker) }}>
                            {speakerLabel(seg.speaker)}
                          </span>
                          <span className="segment-time">
                            {formatTime(seg.start)} – {formatTime(seg.end)}
                          </span>
                        </div>
                        <p>{seg.text}</p>
                      </div>
                    ))}
                  </div>
                ) : videoData.status === "running" || videoData.status === "pending" ? (
                  <div className="transcript-loading">
                    <Loader2 size={22} className="spin" />
                    <p>{stageLabel(videoData.current_stage)}</p>
                  </div>
                ) : (
                  <div className="transcript-empty">
                    <MessageSquareText size={26} />
                    <p>La transcription apparaîtra ici une fois l'analyse terminée.</p>
                  </div>
                )}

                {error && (
                  <div className="error" style={{ margin: "12px 0" }}>
                    <AlertCircle size={16} />
                    <span>{error}</span>
                  </div>
                )}
                {videoData.status === "failed" && (
                  <button
                    className="export-btn retry"
                    onClick={() => retryAnalysis(videoData.id)}
                    style={{ margin: "0 0 12px" }}
                  >
                    <Sparkles size={15} /> Réessayer l'analyse
                  </button>
                )}
                <div className="export-actions">
                  <button className="export-btn secondary" onClick={handleDownloadSubtitles} disabled={!analysis}>
                    <Subtitles size={15} /> Sous-titres (.srt)
                  </button>
                  <button className="export-btn" onClick={handleExport} disabled={!analysis}>
                    <Download size={15} /> Exporter en JSON
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;