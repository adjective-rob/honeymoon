"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { socket } from "@/lib/ws";
import { AGENT_COLORS, SEV_COLORS } from "@/lib/types";
import type { DaemonState, PipelineEvent, LedgerEntry, Finding } from "@/lib/types";

// ---------------------------------------------------------------------------
// Hex cell for the hive
// ---------------------------------------------------------------------------
function HexCell({
  label,
  icon,
  role,
  active,
  pulse,
}: {
  label: string;
  icon: string;
  role: string;
  active: boolean;
  pulse: boolean;
}) {
  const color = AGENT_COLORS[role] || "#6b7280";
  return (
    <motion.div
      className="relative flex flex-col items-center justify-center"
      style={{ width: 90, height: 100 }}
      animate={pulse ? { scale: [1, 1.08, 1] } : {}}
      transition={{ duration: 0.6, repeat: pulse ? Infinity : 0, repeatDelay: 0.4 }}
    >
      <svg viewBox="0 0 100 115" width={90} height={100}>
        <polygon
          points="50,2 95,28 95,80 50,106 5,80 5,28"
          fill={active ? `${color}22` : "rgba(255,255,255,0.02)"}
          stroke={active ? color : "rgba(255,255,255,0.08)"}
          strokeWidth={active ? 2 : 1}
          style={{ transition: "all 0.3s" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl">{icon}</span>
        <span
          className="text-[10px] font-semibold uppercase tracking-wider mt-0.5"
          style={{ color: active ? color : "#6b7280" }}
        >
          {label}
        </span>
      </div>
      {active && (
        <motion.div
          className="absolute -bottom-1 w-2 h-2 rounded-full"
          style={{ background: color }}
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1, repeat: Infinity }}
        />
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Posture gauge
// ---------------------------------------------------------------------------
function PostureGauge({ score, trend }: { score: number | null; trend: string | null }) {
  if (score === null) return null;
  const color = score >= 70 ? "#10b981" : score >= 40 ? "#eab308" : "#ef4444";
  const trendIcon = trend === "improving" ? "\u2191" : trend === "degrading" ? "\u2193" : "\u2192";
  const circumference = 2 * Math.PI * 45;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex items-center gap-4">
      <div className="relative w-24 h-24">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx={50} cy={50} r={45} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={6} />
          <motion.circle
            cx={50} cy={50} r={45} fill="none"
            stroke={color} strokeWidth={6} strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.5, ease: "easeOut" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-2xl font-bold" style={{ color }}>{score}</span>
        </div>
      </div>
      <div>
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Posture</div>
        <div className="text-sm font-semibold" style={{ color }}>
          {trendIcon} {trend || "unknown"}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live event feed
// ---------------------------------------------------------------------------
function EventFeed({ events }: { events: PipelineEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex flex-col gap-0.5 max-h-[500px] overflow-y-auto pr-2">
      <AnimatePresence>
        {events.slice(-50).map((ev, i) => {
          const color = AGENT_COLORS[ev.agent_id] || "#6b7280";
          const icon =
            ev.event_type === "run.started" ? "\u26A1" :
            ev.event_type === "run.completed" ? "\uD83C\uDFC1" :
            ev.event_type?.includes("plan") ? "\uD83E\uDDE0" :
            ev.event_type?.includes("tool") ? "\uD83D\uDEE0\uFE0F" :
            ev.event_type?.includes("security") ? "\uD83D\uDD12" :
            ev.event_type?.includes("finding") ? "\uD83D\uDC1D" :
            "\u2022";

          const summary =
            ev.payload?.command || ev.payload?.tool_name ||
            ev.payload?.status || ev.payload?.verdict || "";

          return (
            <motion.div
              key={`${ev.timestamp}-${i}`}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex items-center gap-2 py-1 px-2 rounded text-xs hover:bg-white/[0.02]"
            >
              <span className="text-sm">{icon}</span>
              <span
                className="font-semibold uppercase text-[9px] tracking-wider min-w-[70px]"
                style={{ color }}
              >
                {ev.agent_id || "system"}
              </span>
              <span className="font-mono text-zinc-500 text-[10px]">
                {ev.event_type}
              </span>
              {summary && (
                <span className="text-zinc-600 truncate max-w-[200px]">{summary}</span>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
      <div ref={bottomRef} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finding card
// ---------------------------------------------------------------------------
function FindingCard({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const color = SEV_COLORS[finding.severity] || "#6b7280";

  return (
    <motion.div
      layout
      className="border rounded-lg overflow-hidden mb-2 cursor-pointer"
      style={{
        background: "rgba(255,255,255,0.03)",
        borderColor: "rgba(255,255,255,0.08)",
      }}
      whileHover={{ borderColor: "rgba(255,255,255,0.15)" }}
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-center gap-3 p-3">
        <span
          className="text-[10px] font-bold uppercase min-w-[50px]"
          style={{ color }}
        >
          {finding.severity}
        </span>
        <span className="text-sm font-medium text-zinc-200 flex-1">
          {finding.title}
        </span>
        <span className="text-[10px] text-zinc-600">{finding.confidence}</span>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="px-3 pb-3 overflow-hidden"
          >
            {finding.evidence && (
              <pre className="text-[11px] font-mono text-zinc-500 bg-black/40 rounded p-2 mb-2 whitespace-pre-wrap break-all">
                {finding.evidence}
              </pre>
            )}
            {finding.analysis && (
              <p className="text-xs text-zinc-400 leading-relaxed">{finding.analysis}</p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Command buttons
// ---------------------------------------------------------------------------
function CommandBar({ onCommand, running }: { onCommand: (cmd: string) => void; running: string | null }) {
  const commands = [
    { id: "scan", label: "Scan", icon: "\uD83D\uDD0D", color: "#3b82f6" },
    { id: "simulate", label: "Simulate", icon: "\uD83C\uDFAF", color: "#ef4444" },
    { id: "harden", label: "Harden", icon: "\uD83D\uDEE1\uFE0F", color: "#f59e0b" },
    { id: "deep", label: "Deep Scan", icon: "\uD83D\uDC1D", color: "#10b981" },
  ];

  return (
    <div className="flex gap-2">
      {commands.map((cmd) => (
        <motion.button
          key={cmd.id}
          onClick={() => onCommand(cmd.id)}
          disabled={!!running}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 disabled:opacity-40 transition-all"
          style={{
            background: running === cmd.id ? `${cmd.color}33` : "rgba(255,255,255,0.04)",
            border: `1px solid ${running === cmd.id ? cmd.color : "rgba(255,255,255,0.08)"}`,
            color: running === cmd.id ? cmd.color : "#9ca3af",
          }}
        >
          <span>{cmd.icon}</span>
          {running === cmd.id ? "Running..." : cmd.label}
        </motion.button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------
export default function Home() {
  const [connected, setConnected] = useState(false);
  const [state, setState] = useState<DaemonState | null>(null);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);

  // Connect to daemon
  useEffect(() => {
    socket.connect();

    const unsubs = [
      socket.on("connected", () => setConnected(true)),
      socket.on("disconnected", () => setConnected(false)),
      socket.on("state", (data: DaemonState) => {
        setState(data);
        // Extract findings from ledger
        const allFindings: Finding[] = [];
        for (const report of data.event_buffer || []) {
          if (report.payload?.findings) {
            allFindings.push(...report.payload.findings);
          }
        }
        if (allFindings.length) setFindings(allFindings);
      }),
      socket.on("*", (data: any) => {
        if (data.event_type) {
          setEvents((prev) => [...prev.slice(-200), data as PipelineEvent]);

          // Track active agent
          if (data.event_type === "pipeline.step_started") {
            setActiveAgent(data.payload?.agent_role || null);
          } else if (data.event_type === "pipeline.step_completed" || data.event_type === "run.completed") {
            setActiveAgent(null);
          }

          // Track findings from submit_findings
          if (data.event_type === "agent.submit_findings" && data.payload?.findings) {
            setFindings((prev) => [...prev, ...data.payload.findings]);
          }
        }
        if (data.type === "command_completed") {
          setRunning(null);
          // Refresh state
          socket.send("get_state");
        }
      }),
    ];

    return () => {
      unsubs.forEach((unsub) => unsub());
      socket.disconnect();
    };
  }, []);

  const handleCommand = useCallback((cmd: string) => {
    setRunning(cmd);
    setEvents([]);
    socket.send(cmd);
  }, []);

  const agents = [
    { role: "planner", label: "Queen", icon: "\uD83D\uDC51" },
    { role: "implementer", label: "Builder", icon: "\uD83C\uDFD7\uFE0F" },
    { role: "debugger", label: "Nurse", icon: "\uD83E\uDE7A" },
    { role: "security", label: "Guard", icon: "\uD83D\uDC1D" },
    { role: "testgen", label: "Inspector", icon: "\uD83D\uDD0D" },
    { role: "release", label: "Waggle", icon: "\uD83D\uDC83" },
    { role: "archivist", label: "Keeper", icon: "\uD83C\uDF6F" },
  ];

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
              <span className="text-2xl">{"\uD83C\uDF6F"}</span> HONEYMOON
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              {state?.repo_name || "Not connected"} &middot;{" "}
              <span className={connected ? "text-emerald-500" : "text-red-500"}>
                {connected ? "Live" : "Connecting..."}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-6">
            <PostureGauge score={state?.posture ?? null} trend={state?.trend ?? null} />
            <div className="text-right">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Runs</div>
              <div className="font-mono text-lg font-bold text-zinc-300">
                {state?.hardening_runs ?? 0}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest">Reports</div>
              <div className="font-mono text-lg font-bold text-zinc-300">
                {state?.report_count ?? 0}
              </div>
            </div>
          </div>
        </div>

        {/* Command bar */}
        <div className="mb-8">
          <CommandBar onCommand={handleCommand} running={running} />
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-12 gap-6">
          {/* Hive */}
          <div className="col-span-5">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-3">
              The Hive
            </div>
            <div className="flex flex-wrap justify-center gap-1 p-4 rounded-xl border border-white/[0.06] bg-white/[0.02]">
              {agents.map((a) => (
                <HexCell
                  key={a.role}
                  label={a.label}
                  icon={a.icon}
                  role={a.role}
                  active={activeAgent === a.role}
                  pulse={activeAgent === a.role}
                />
              ))}
            </div>

            {/* Findings */}
            {findings.length > 0 && (
              <div className="mt-6">
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-3">
                  Findings ({findings.length})
                </div>
                {findings.slice(-10).map((f, i) => (
                  <FindingCard key={`${f.title}-${i}`} finding={f} />
                ))}
              </div>
            )}
          </div>

          {/* Event stream */}
          <div className="col-span-7">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-3">
              {running ? (
                <span className="text-amber-500">
                  {"\u26A1"} Running {running}...
                </span>
              ) : (
                "Event Stream"
              )}
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 min-h-[400px]">
              {events.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[400px] text-zinc-600">
                  <span className="text-4xl mb-3">{"\uD83D\uDC1D"}</span>
                  <p className="text-sm">
                    {connected
                      ? "Click a command to start. Events will stream here live."
                      : "Start the daemon: honeymoon serve --repo ."}
                  </p>
                </div>
              ) : (
                <EventFeed events={events} />
              )}
            </div>

            {/* Ledger summary */}
            {state?.ledger && state.ledger.length > 0 && (
              <div className="mt-6">
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-3">
                  Hardening Ledger
                </div>
                <div className="flex gap-1">
                  {state.ledger.slice(-20).map((entry, i) => {
                    const color =
                      entry.posture_score >= 70 ? "#10b981" :
                      entry.posture_score >= 40 ? "#eab308" : "#ef4444";
                    return (
                      <motion.div
                        key={i}
                        initial={{ height: 0 }}
                        animate={{ height: `${entry.posture_score}%` }}
                        transition={{ duration: 0.5, delay: i * 0.05 }}
                        className="flex-1 rounded-t"
                        style={{
                          background: color,
                          minHeight: 4,
                          maxHeight: 60,
                          opacity: 0.7,
                        }}
                        title={`Run #${entry.total_runs}: ${entry.posture_score}/100`}
                      />
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-12 pt-4 border-t border-white/[0.04] flex justify-between text-[11px] text-zinc-700">
          <span>HONEYMOON Dashboard &middot; Adjective LLC</span>
          <span>
            {connected ? "\uD83D\uDFE2" : "\uD83D\uDD34"} ws://127.0.0.1:4200
          </span>
        </div>
      </div>
    </div>
  );
}
