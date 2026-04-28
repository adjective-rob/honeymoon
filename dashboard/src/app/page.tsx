"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield, Search, Target, Bug, Hexagon, Wifi, WifiOff,
  Play, Loader2, CheckCircle2, AlertTriangle, XCircle,
  ChevronRight, Lock, FileSearch, Zap, Activity,
  TrendingUp, TrendingDown, Minus, ScrollText,
  ExternalLink, Clock, DollarSign, FileCheck, ClipboardList,
} from "lucide-react";
import { socket } from "@/lib/ws";
import type { DaemonState, LedgerEntry, Finding, Report } from "@/lib/types";

// ---------------------------------------------------------------------------
// Severity + Agent config
// ---------------------------------------------------------------------------
const SEV = {
  critical: { color: "#ef4444", bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.3)", icon: XCircle },
  high:     { color: "#f97316", bg: "rgba(249,115,22,0.12)", border: "rgba(249,115,22,0.3)", icon: AlertTriangle },
  medium:   { color: "#eab308", bg: "rgba(234,179,8,0.12)",  border: "rgba(234,179,8,0.3)",  icon: AlertTriangle },
  low:      { color: "#3b82f6", bg: "rgba(59,130,246,0.12)", border: "rgba(59,130,246,0.3)", icon: Shield },
  info:     { color: "#6b7280", bg: "rgba(255,255,255,0.04)", border: "rgba(255,255,255,0.1)", icon: FileSearch },
};

const AGENTS = [
  { role: "planner",     label: "Queen",     color: "#f59e0b" },
  { role: "implementer", label: "Builder",   color: "#eab308" },
  { role: "debugger",    label: "Nurse",     color: "#ef4444" },
  { role: "security",    label: "Guard",     color: "#10b981" },
  { role: "testgen",     label: "Inspector", color: "#14b8a6" },
  { role: "release",     label: "Waggle",    color: "#06b6d4" },
  { role: "archivist",   label: "Keeper",    color: "#a855f7" },
];

// ---------------------------------------------------------------------------
// Posture gauge
// ---------------------------------------------------------------------------
function PostureGauge({ score, trend }: { score: number | null; trend: string | null }) {
  if (score === null) return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-white/[0.06] bg-white/[0.02]">
      <Shield className="w-5 h-5 text-zinc-600" />
      <span className="text-sm text-zinc-500">No posture data</span>
    </div>
  );

  const color = score >= 70 ? "#10b981" : score >= 40 ? "#eab308" : "#ef4444";
  const TrendIcon = trend === "improving" ? TrendingUp : trend === "degrading" ? TrendingDown : Minus;
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex items-center gap-4">
      <div className="relative w-20 h-20">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx={50} cy={50} r={40} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={5} />
          <motion.circle
            cx={50} cy={50} r={40} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.2, ease: "easeOut" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-xl font-bold" style={{ color }}>{score}</span>
        </div>
      </div>
      <div>
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Posture</div>
        <div className="flex items-center gap-1 mt-0.5">
          <TrendIcon className="w-3.5 h-3.5" style={{ color }} />
          <span className="text-xs font-medium" style={{ color }}>{trend || "unknown"}</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hex hive cell
// ---------------------------------------------------------------------------
function HiveCell({ label, color, active }: { label: string; color: string; active: boolean }) {
  return (
    <motion.div
      className="relative flex flex-col items-center justify-center"
      style={{ width: 80, height: 90 }}
      animate={active ? { scale: [1, 1.06, 1] } : {}}
      transition={{ duration: 0.8, repeat: active ? Infinity : 0, repeatDelay: 0.3 }}
    >
      <svg viewBox="0 0 100 115" width={80} height={90}>
        <polygon
          points="50,2 95,28 95,80 50,106 5,80 5,28"
          fill={active ? `${color}20` : "rgba(255,255,255,0.015)"}
          stroke={active ? color : "rgba(255,255,255,0.07)"}
          strokeWidth={active ? 2.5 : 1}
          style={{ transition: "all 0.4s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5">
        <Hexagon className="w-4 h-4" style={{ color: active ? color : "#4b5563" }} />
        <span
          className="text-[9px] font-bold uppercase tracking-widest"
          style={{ color: active ? color : "#4b5563" }}
        >
          {label}
        </span>
      </div>
      {active && (
        <motion.div
          className="absolute bottom-1 w-1.5 h-1.5 rounded-full"
          style={{ background: color }}
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
        />
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Event stream
// ---------------------------------------------------------------------------
interface StreamEvent {
  type: string;
  line?: string;
  agent?: string;
  tool?: string;
  detail?: string;
  event_name?: string;
  action?: string;
  returncode?: number;
}

function EventStream({ events }: { events: StreamEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const getIcon = (ev: StreamEvent) => {
    if (ev.type === "agent_call") return <Zap className="w-3 h-3 text-amber-500" />;
    if (ev.type === "tool_call") return <Play className="w-3 h-3 text-blue-400" />;
    if (ev.type === "pipeline_event") return <Activity className="w-3 h-3 text-purple-400" />;
    if (ev.type === "plan_ready") return <CheckCircle2 className="w-3 h-3 text-green-400" />;
    if (ev.type === "complete") return <CheckCircle2 className="w-3 h-3 text-emerald-400" />;
    if (ev.type === "ledger_update") return <Shield className="w-3 h-3 text-amber-400" />;
    if (ev.type === "command_started") return <Loader2 className="w-3 h-3 text-amber-500 animate-spin" />;
    if (ev.type === "command_completed") return ev.returncode === 0
      ? <CheckCircle2 className="w-3 h-3 text-green-500" />
      : <XCircle className="w-3 h-3 text-red-500" />;
    return <ChevronRight className="w-3 h-3 text-zinc-600" />;
  };

  const getLabel = (ev: StreamEvent) => {
    if (ev.type === "agent_call") return `${ev.agent} → ${ev.detail || ""}`;
    if (ev.type === "tool_call") return `${ev.agent || "agent"} called ${ev.tool}`;
    if (ev.type === "pipeline_event") return ev.event_name || "";
    if (ev.type === "plan_ready") return "Plan ready";
    if (ev.type === "complete") return ev.line || "Complete";
    if (ev.type === "ledger_update") return ev.line || "Ledger updated";
    if (ev.type === "command_started") return `Starting ${ev.action}...`;
    if (ev.type === "command_completed") return `${ev.action} finished (exit ${ev.returncode})`;
    // Raw output — clean up loguru prefix
    const line = ev.line || "";
    const cleaned = line.replace(/^\d{2}:\d{2}:\d{2}\s*\|\s*\w+\s*\|\s*/, "");
    return cleaned;
  };

  return (
    <div className="flex flex-col gap-px max-h-[520px] overflow-y-auto pr-1 custom-scrollbar">
      <AnimatePresence initial={false}>
        {events.slice(-80).map((ev, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
            className="flex items-start gap-2 py-1.5 px-2 rounded hover:bg-white/[0.02] group"
          >
            <span className="mt-0.5 flex-shrink-0">{getIcon(ev)}</span>
            <span className="text-[11px] text-zinc-400 leading-relaxed font-mono truncate">
              {getLabel(ev)}
            </span>
          </motion.div>
        ))}
      </AnimatePresence>
      <div ref={endRef} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Command buttons
// ---------------------------------------------------------------------------
function CommandBar({ onCommand, running }: { onCommand: (cmd: string) => void; running: string | null }) {
  const commands = [
    { id: "scan",     label: "Scan",     icon: Search,  desc: "Quick investigate" },
    { id: "simulate", label: "Simulate", icon: Target,  desc: "Red/Blue attack sim" },
    { id: "harden",   label: "Harden",   icon: Shield,  desc: "Posture tracking" },
    { id: "deep",     label: "Deep Scan", icon: Bug,    desc: "Full audit + SPEC" },
  ];

  return (
    <div className="grid grid-cols-4 gap-2">
      {commands.map((cmd) => {
        const isRunning = running === cmd.id;
        const Icon = cmd.icon;
        return (
          <motion.button
            key={cmd.id}
            onClick={() => onCommand(cmd.id)}
            disabled={!!running}
            whileHover={running ? {} : { y: -2 }}
            whileTap={running ? {} : { scale: 0.98 }}
            className="relative px-4 py-3 rounded-xl text-left disabled:opacity-40 transition-all overflow-hidden cursor-pointer disabled:cursor-not-allowed"
            style={{
              background: isRunning ? "rgba(245,158,11,0.08)" : "rgba(255,255,255,0.02)",
              border: `1px solid ${isRunning ? "rgba(245,158,11,0.3)" : "rgba(255,255,255,0.06)"}`,
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              {isRunning ? (
                <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
              ) : (
                <Icon className="w-4 h-4 text-zinc-400" />
              )}
              <span className="text-sm font-semibold text-zinc-200">{cmd.label}</span>
            </div>
            <span className="text-[10px] text-zinc-500">{isRunning ? "Running..." : cmd.desc}</span>
          </motion.button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finding card (compact)
// ---------------------------------------------------------------------------
function FindingPill({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const sev = SEV[finding.severity] || SEV.info;
  const Icon = sev.icon;
  return (
    <div
      className="rounded-lg text-xs cursor-pointer transition-all"
      style={{ background: sev.bg, border: `1px solid ${sev.border}` }}
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-center gap-2 px-3 py-2">
        <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: sev.color }} />
        <span className="font-medium truncate flex-1" style={{ color: sev.color }}>
          {finding.title}
        </span>
        <ChevronRight
          className="w-3 h-3 transition-transform flex-shrink-0"
          style={{ color: sev.color, transform: open ? "rotate(90deg)" : "rotate(0)" }}
        />
      </div>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-2 space-y-1.5">
              {finding.evidence && (
                <pre className="text-[10px] font-mono text-zinc-500 bg-black/30 rounded p-2 whitespace-pre-wrap break-all leading-relaxed">
                  {finding.evidence}
                </pre>
              )}
              {finding.analysis && (
                <p className="text-[11px] text-zinc-400 leading-relaxed">{finding.analysis}</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats card
// ---------------------------------------------------------------------------
function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="px-4 py-3">
      <div className="text-[9px] text-zinc-500 uppercase tracking-widest mb-1">{label}</div>
      <div className="font-mono text-lg font-bold text-zinc-200">{value}</div>
      {sub && <div className="text-[10px] text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mission color map
// ---------------------------------------------------------------------------
const MISSION_COLORS: Record<string, { color: string; bg: string; border: string }> = {
  investigate: { color: "#3b82f6", bg: "rgba(59,130,246,0.12)", border: "rgba(59,130,246,0.3)" },
  bulk:        { color: "#a855f7", bg: "rgba(168,85,247,0.12)", border: "rgba(168,85,247,0.3)" },
  monitor:     { color: "#10b981", bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.3)" },
  scan:        { color: "#eab308", bg: "rgba(234,179,8,0.12)",  border: "rgba(234,179,8,0.3)"  },
  simulate:    { color: "#ef4444", bg: "rgba(239,68,68,0.12)",  border: "rgba(239,68,68,0.3)"  },
  harden:      { color: "#06b6d4", bg: "rgba(6,182,212,0.12)",  border: "rgba(6,182,212,0.3)"  },
  deep:        { color: "#f97316", bg: "rgba(249,115,22,0.12)", border: "rgba(249,115,22,0.3)" },
};

const DEFAULT_MISSION_STYLE = { color: "#6b7280", bg: "rgba(255,255,255,0.04)", border: "rgba(255,255,255,0.1)" };

// ---------------------------------------------------------------------------
// Report card
// ---------------------------------------------------------------------------
function ReportCard({ report }: { report: Report }) {
  const [open, setOpen] = useState(false);
  const style = MISSION_COLORS[report.mission] || DEFAULT_MISSION_STYLE;
  const ts = new Date(report.timestamp);
  const timeStr = ts.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
  const cost = report.budget?.total_cost != null
    ? `$${Number(report.budget.total_cost).toFixed(4)}`
    : report.budget?.cost != null
    ? `$${Number(report.budget.cost).toFixed(4)}`
    : null;

  return (
    <motion.div
      layout
      className="rounded-lg text-xs cursor-pointer transition-all"
      style={{ background: "rgba(255,255,255,0.02)", border: `1px solid rgba(255,255,255,0.06)` }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2.5 hover:bg-white/[0.02] rounded-lg transition-colors"
        onClick={() => setOpen(!open)}
      >
        {/* Mission badge */}
        <span
          className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider flex-shrink-0"
          style={{ background: style.bg, color: style.color, border: `1px solid ${style.border}` }}
        >
          {report.mission}
        </span>

        {/* Timestamp */}
        <span className="flex items-center gap-1 text-zinc-500 flex-shrink-0">
          <Clock className="w-3 h-3" />
          {timeStr}
        </span>

        {/* Finding count */}
        <span className="flex items-center gap-1 text-zinc-400 flex-shrink-0">
          <AlertTriangle className="w-3 h-3" />
          {report.finding_count}
        </span>

        {/* Cost */}
        {cost && (
          <span className="flex items-center gap-1 text-zinc-500 flex-shrink-0">
            <DollarSign className="w-3 h-3" />
            {cost}
          </span>
        )}

        {/* Spacer + signed + chevron */}
        <span className="flex-1" />
        {report.signed && (
          <span title="Signed"><FileCheck className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" /></span>
        )}
        <ChevronRight
          className="w-3 h-3 text-zinc-600 transition-transform flex-shrink-0"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0)" }}
        />
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 space-y-3">
              {/* Objective */}
              {report.objective && (
                <p className="text-[11px] text-zinc-400 leading-relaxed italic border-l-2 pl-2"
                   style={{ borderColor: style.color }}>
                  {report.objective}
                </p>
              )}

              {/* Summary */}
              {report.summary && (
                <p className="text-[11px] text-zinc-400 leading-relaxed">
                  {report.summary}
                </p>
              )}

              {/* Findings */}
              {report.findings && report.findings.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[9px] text-zinc-500 uppercase tracking-widest">
                    Findings ({report.findings.length})
                  </div>
                  {report.findings.map((f, i) => (
                    <FindingPill key={i} finding={f} />
                  ))}
                </div>
              )}

              {/* Open HTML report link */}
              <a
                href={`http://127.0.0.1:4201/api/report/${report.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-[11px] font-medium hover:underline transition-colors"
                style={{ color: style.color }}
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink className="w-3 h-3" />
                Open full report
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Reports panel
// ---------------------------------------------------------------------------
function ReportsPanel({ reports }: { reports: Report[] }) {
  if (reports.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[500px] text-zinc-600">
        <ClipboardList className="w-12 h-12 text-zinc-800 mb-4" />
        <p className="text-sm font-medium text-zinc-500">No reports yet</p>
        <p className="text-xs text-zinc-600 mt-1">Run a scan to generate reports</p>
      </div>
    );
  }

  return (
    <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1 custom-scrollbar">
      {reports.map((report) => (
        <ReportCard key={report.id} report={report} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ledger bar chart
// ---------------------------------------------------------------------------
function LedgerChart({ entries }: { entries: LedgerEntry[] }) {
  if (!entries.length) return null;
  return (
    <div className="flex items-end gap-0.5 h-12">
      {entries.slice(-30).map((e, i) => {
        const color = e.posture_score >= 70 ? "#10b981" : e.posture_score >= 40 ? "#eab308" : "#ef4444";
        return (
          <motion.div
            key={i}
            initial={{ height: 0 }}
            animate={{ height: `${Math.max(e.posture_score, 4)}%` }}
            transition={{ duration: 0.4, delay: i * 0.03 }}
            className="flex-1 rounded-t min-w-[3px]"
            style={{ background: color, opacity: 0.6 }}
            title={`#${e.total_runs}: ${e.posture_score}/100`}
          />
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function Home() {
  const [connected, setConnected] = useState(false);
  const [state, setState] = useState<DaemonState | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [latestSummary, setLatestSummary] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [rightTab, setRightTab] = useState<"events" | "reports">("events");

  const fetchReports = useCallback(() => {
    socket.send("get_reports");
  }, []);

  useEffect(() => {
    socket.connect();

    const unsubs = [
      socket.on("connected", () => {
        setConnected(true);
        // Fetch reports on connect
        setTimeout(fetchReports, 300);
      }),
      socket.on("disconnected", () => setConnected(false)),

      socket.on("state", (data: DaemonState) => {
        setState(data);
        setRunning(data.running || null);
        // Always fetch reports when we get state
        fetchReports();
      }),

      // Handle reports response directly
      socket.on("reports", (data: any) => {
        if (data.reports) {
          setReports(data.reports);
        }
        if (data.reports?.length) {
          const latest = data.reports[0];
          if (latest?.findings?.length) setFindings(latest.findings);
          if (latest?.summary) setLatestSummary(latest.summary);
        }
      }),

      socket.on("*", (data: any) => {
        // Stream events
        if (data.type && data.type !== "state" && data.type !== "reports") {
          setEvents((prev) => [...prev.slice(-300), data as StreamEvent]);
        }

        // Track active agent from output parsing
        if (data.type === "agent_call" && data.agent) {
          setActiveAgent(data.agent);
        }
        if (data.type === "tool_call" && data.agent) {
          setActiveAgent(data.agent);
        }
        if (data.type === "command_completed") {
          setActiveAgent(null);
          setRunning(null);
          // Refresh state and reports after command finishes
          setTimeout(() => {
            socket.send("get_state");
            fetchReports();
          }, 1000);
        }
        if (data.type === "command_started") {
          setRunning(data.action);
        }

        // Handle reports response
        if (data.type === "reports" && data.reports) {
          setReports(data.reports);
          if (data.reports.length) {
            const latest = data.reports[0];
            if (latest?.findings?.length) {
              setFindings(latest.findings);
            }
            if (latest?.summary) {
              setLatestSummary(latest.summary);
            }
          }
        }
      }),
    ];

    return () => {
      unsubs.forEach((fn) => fn());
      socket.disconnect();
    };
  }, [fetchReports]);

  const handleCommand = useCallback((cmd: string) => {
    setRunning(cmd);
    setEvents([]);
    setActiveAgent(null);
    socket.send(cmd);
  }, []);

  return (
    <div className="min-h-screen p-5">
      <div className="max-w-[1400px] mx-auto">

        {/* Header */}
        <header className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <Hexagon className="w-5 h-5 text-amber-500" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-zinc-100">HONEYMOON</h1>
              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-zinc-500">{state?.repo_name || "—"}</span>
                <span className="flex items-center gap-1">
                  {connected ? (
                    <><Wifi className="w-3 h-3 text-emerald-500" /><span className="text-emerald-500">Live</span></>
                  ) : (
                    <><WifiOff className="w-3 h-3 text-red-500" /><span className="text-red-500">Disconnected</span></>
                  )}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <PostureGauge score={state?.posture ?? null} trend={state?.trend ?? null} />
            <div className="flex gap-px rounded-lg border border-white/[0.06] overflow-hidden">
              <Stat label="Runs" value={state?.hardening_runs ?? 0} />
              <Stat label="Reports" value={state?.report_count ?? 0} />
              <Stat label="Issues" value={state?.finding_count ?? 0} />
            </div>
          </div>
        </header>

        {/* Commands */}
        <section className="mb-6">
          <CommandBar onCommand={handleCommand} running={running} />
        </section>

        {/* Main grid */}
        <div className="grid grid-cols-12 gap-5">

          {/* Left: Hive + Findings */}
          <div className="col-span-4 space-y-5">
            {/* Hive */}
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="text-[9px] text-zinc-500 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                <Hexagon className="w-3 h-3" /> The Hive
              </div>
              <div className="flex flex-wrap justify-center gap-0.5">
                {AGENTS.map((a) => (
                  <HiveCell
                    key={a.role}
                    label={a.label}
                    color={a.color}
                    active={activeAgent === a.role}
                  />
                ))}
              </div>
            </div>

            {/* Findings */}
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="text-[9px] text-zinc-500 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                <Lock className="w-3 h-3" /> Latest Findings
                {findings.length > 0 && (
                  <span className="ml-auto text-zinc-600 normal-case tracking-normal">{findings.length} found</span>
                )}
              </div>
              {latestSummary && (
                <p className="text-[11px] text-zinc-400 leading-relaxed mb-3 pb-3 border-b border-white/[0.06]">
                  {latestSummary}
                </p>
              )}
              {findings.length === 0 ? (
                <div className="text-xs text-zinc-600 text-center py-6">
                  Run a scan to see findings
                </div>
              ) : (
                <div className="space-y-1.5">
                  {findings.slice(0, 10).map((f, i) => (
                    <FindingPill key={i} finding={f} />
                  ))}
                </div>
              )}
            </div>

            {/* Ledger */}
            {state?.ledger && state.ledger.length > 0 && (
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="text-[9px] text-zinc-500 uppercase tracking-widest mb-3 flex items-center gap-1.5">
                  <ScrollText className="w-3 h-3" /> Hardening Ledger
                </div>
                <LedgerChart entries={state.ledger} />
              </div>
            )}
          </div>

          {/* Right: Tabbed panel (Event Stream / Reports) */}
          <div className="col-span-8">
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 min-h-[600px]">
              {/* Tab bar */}
              <div className="flex items-center gap-2 mb-3">
                {([
                  { id: "events" as const, label: "Event Stream", icon: Activity },
                  { id: "reports" as const, label: "Reports", icon: ClipboardList, count: reports.length },
                ]).map((tab) => {
                  const active = rightTab === tab.id;
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setRightTab(tab.id)}
                      className="relative px-3 py-1.5 rounded-lg text-[10px] uppercase tracking-widest font-medium transition-all cursor-pointer flex items-center gap-1.5"
                      style={{
                        background: active ? "rgba(245,158,11,0.08)" : "transparent",
                        border: `1px solid ${active ? "rgba(245,158,11,0.3)" : "rgba(255,255,255,0.06)"}`,
                        color: active ? "#f59e0b" : "#71717a",
                      }}
                    >
                      <Icon className="w-3 h-3" />
                      {tab.label}
                      {tab.count != null && tab.count > 0 && (
                        <span
                          className="ml-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold"
                          style={{
                            background: active ? "rgba(245,158,11,0.15)" : "rgba(255,255,255,0.06)",
                            color: active ? "#f59e0b" : "#71717a",
                          }}
                        >
                          {tab.count}
                        </span>
                      )}
                    </button>
                  );
                })}

                {/* Running indicator (shown regardless of tab) */}
                {running && (
                  <div className="ml-auto flex items-center gap-1.5 text-[9px] text-amber-500 uppercase tracking-widest">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Running {running}...
                  </div>
                )}
              </div>

              {/* Tab content */}
              {rightTab === "events" ? (
                events.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-[500px] text-zinc-600">
                    <Hexagon className="w-12 h-12 text-zinc-800 mb-4" />
                    <p className="text-sm font-medium text-zinc-500">
                      {connected ? "Click a command to start" : "Waiting for daemon..."}
                    </p>
                    <p className="text-xs text-zinc-600 mt-1">
                      {connected ? "Events will stream here live" : "honeymoon serve --repo ."}
                    </p>
                  </div>
                ) : (
                  <EventStream events={events} />
                )
              ) : (
                <ReportsPanel reports={reports} />
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-8 pt-4 border-t border-white/[0.04] flex justify-between text-[10px] text-zinc-700">
          <span>HONEYMOON &middot; Adjective LLC</span>
          <span className="flex items-center gap-1">
            {connected ? <Wifi className="w-2.5 h-2.5 text-emerald-600" /> : <WifiOff className="w-2.5 h-2.5 text-red-600" />}
            ws://127.0.0.1:4200
          </span>
        </footer>
      </div>
    </div>
  );
}
