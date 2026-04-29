"use client";

import { Shield, ArrowRight, Lock, Hexagon, FileCheck, Key, Fingerprint, GitBranch, CheckCircle2, XCircle, ChevronDown } from "lucide-react";

export default function ZephyrPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0b] text-zinc-200 p-8">
      <div className="max-w-4xl mx-auto">

        {/* Header */}
        <div className="mb-12">
          <a href="/" className="text-xs text-zinc-500 hover:text-amber-500 transition-colors mb-4 inline-block">&larr; Back to Dashboard</a>
          <h1 className="text-4xl font-bold tracking-tight text-white mb-3">
            Zephyr <span className="text-amber-500">SBOF</span>
          </h1>
          <p className="text-lg text-zinc-400 max-w-2xl leading-relaxed">
            Signed Binary Object Format. A cryptographic attestation layer that signs every action,
            report, and ledger entry so you can prove what happened, when, and by whom.
          </p>
        </div>

        {/* Diagram 1: How Zephyr Signing Works */}
        <section className="mb-16">
          <h2 className="text-sm font-bold text-zinc-500 uppercase tracking-widest mb-6">How It Works</h2>

          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8 mb-6">
            {/* Flow diagram */}
            <div className="flex items-center justify-between gap-4 mb-8 flex-wrap">
              {/* Step 1: Action */}
              <div className="flex-1 min-w-[140px]">
                <div className="w-16 h-16 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mx-auto mb-3">
                  <Hexagon className="w-8 h-8 text-amber-500" />
                </div>
                <div className="text-center">
                  <div className="text-sm font-semibold text-white">Action</div>
                  <div className="text-[11px] text-zinc-500 mt-1">Agent scans, tool executes,<br />finding submitted</div>
                </div>
              </div>

              <ArrowRight className="w-5 h-5 text-zinc-700 flex-shrink-0" />

              {/* Step 2: Serialize */}
              <div className="flex-1 min-w-[140px]">
                <div className="w-16 h-16 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto mb-3">
                  <FileCheck className="w-8 h-8 text-blue-400" />
                </div>
                <div className="text-center">
                  <div className="text-sm font-semibold text-white">Serialize</div>
                  <div className="text-[11px] text-zinc-500 mt-1">Event → deterministic<br />JSON payload</div>
                </div>
              </div>

              <ArrowRight className="w-5 h-5 text-zinc-700 flex-shrink-0" />

              {/* Step 3: Sign */}
              <div className="flex-1 min-w-[140px]">
                <div className="w-16 h-16 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-3">
                  <Key className="w-8 h-8 text-emerald-400" />
                </div>
                <div className="text-center">
                  <div className="text-sm font-semibold text-white">Sign</div>
                  <div className="text-[11px] text-zinc-500 mt-1">Ed25519 private key<br />produces signature</div>
                </div>
              </div>

              <ArrowRight className="w-5 h-5 text-zinc-700 flex-shrink-0" />

              {/* Step 4: Append */}
              <div className="flex-1 min-w-[140px]">
                <div className="w-16 h-16 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center mx-auto mb-3">
                  <Lock className="w-8 h-8 text-purple-400" />
                </div>
                <div className="text-center">
                  <div className="text-sm font-semibold text-white">Append</div>
                  <div className="text-[11px] text-zinc-500 mt-1">Signed envelope →<br />append-only ledger</div>
                </div>
              </div>
            </div>

            {/* Signing envelope example */}
            <div className="rounded-xl bg-black/40 border border-white/[0.06] p-5 font-mono text-[12px] leading-relaxed">
              <div className="text-zinc-500 mb-2">// Signed envelope (audit.jsonl)</div>
              <div className="text-zinc-300">{"{"}</div>
              <div className="pl-4">
                <span className="text-amber-400">&quot;label&quot;</span>: <span className="text-emerald-400">&quot;act-7f3a2b1e&quot;</span>,
              </div>
              <div className="pl-4">
                <span className="text-amber-400">&quot;payload&quot;</span>: <span className="text-zinc-500">&quot;{'{'}event_type: tool.executed, command: npm test, ...{'}'}&quot;</span>,
              </div>
              <div className="pl-4">
                <span className="text-amber-400">&quot;signer&quot;</span>: <span className="text-blue-400">&quot;1/QL5bc6bfAIWy3uJ1KYEgGW9...&quot;</span>,
              </div>
              <div className="pl-4">
                <span className="text-amber-400">&quot;signature&quot;</span>: <span className="text-emerald-400">&quot;jNxv/11r7SrmeFkupPVYoT04LX3L41dE...&quot;</span>,
              </div>
              <div className="pl-4">
                <span className="text-amber-400">&quot;timestamp&quot;</span>: <span className="text-zinc-400">&quot;2026-04-28T05:21:39Z&quot;</span>
              </div>
              <div className="text-zinc-300">{"}"}</div>
            </div>
          </div>

          {/* Two properties */}
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-5">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <span className="font-semibold text-emerald-400">Authenticity</span>
              </div>
              <p className="text-sm text-zinc-400 leading-relaxed">
                The signature proves who produced the data. Only the holder of the private key
                could have generated this signature. If the key lives on your machine, the report
                came from your Honeymoon instance.
              </p>
            </div>
            <div className="rounded-xl border border-blue-500/20 bg-blue-500/[0.04] p-5">
              <div className="flex items-center gap-2 mb-2">
                <Shield className="w-5 h-5 text-blue-400" />
                <span className="font-semibold text-blue-400">Integrity</span>
              </div>
              <p className="text-sm text-zinc-400 leading-relaxed">
                Change one character in the report and the signature verification fails.
                You cannot edit a finding&apos;s severity from HIGH to LOW and keep the signature valid.
                The data is tamper-evident.
              </p>
            </div>
          </div>
        </section>

        {/* Diagram 2: Gatekeeper — How It Actually Works */}
        <section className="mb-16">
          <h2 className="text-sm font-bold text-zinc-500 uppercase tracking-widest mb-6">Gatekeeper: Git Pre-Push Enforcement</h2>

          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8 mb-6">

            {/* The real flow */}
            <div className="flex items-center justify-between gap-3 mb-8 flex-wrap">
              <div className="flex-1 min-w-[120px] text-center">
                <div className="w-14 h-14 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mx-auto mb-2">
                  <GitBranch className="w-7 h-7 text-amber-500" />
                </div>
                <div className="text-xs font-semibold text-white">git push</div>
                <div className="text-[10px] text-zinc-500">Developer pushes</div>
              </div>

              <ArrowRight className="w-4 h-4 text-zinc-700 flex-shrink-0" />

              <div className="flex-1 min-w-[120px] text-center">
                <div className="w-14 h-14 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto mb-2">
                  <Fingerprint className="w-7 h-7 text-blue-400" />
                </div>
                <div className="text-xs font-semibold text-white">zephyr digest</div>
                <div className="text-[10px] text-zinc-500">Hash all artifacts</div>
              </div>

              <ArrowRight className="w-4 h-4 text-zinc-700 flex-shrink-0" />

              <div className="flex-1 min-w-[120px] text-center">
                <div className="w-14 h-14 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center mx-auto mb-2">
                  <FileCheck className="w-7 h-7 text-purple-400" />
                </div>
                <div className="text-xs font-semibold text-white">sbof-export</div>
                <div className="text-[10px] text-zinc-500">Bundle signatures</div>
              </div>

              <ArrowRight className="w-4 h-4 text-zinc-700 flex-shrink-0" />

              <div className="flex-1 min-w-[120px] text-center">
                <div className="w-14 h-14 rounded-full border-2 border-red-500/40 bg-red-500/10 flex items-center justify-center mx-auto mb-2">
                  <Shield className="w-7 h-7 text-red-400" />
                </div>
                <div className="text-xs font-semibold text-red-400">GATEKEEPER</div>
                <div className="text-[10px] text-zinc-500">Check trust policy</div>
              </div>

              <ArrowRight className="w-4 h-4 text-zinc-700 flex-shrink-0" />

              <div className="flex-1 min-w-[120px] text-center">
                <div className="w-14 h-14 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-2">
                  <CheckCircle2 className="w-7 h-7 text-emerald-400" />
                </div>
                <div className="text-xs font-semibold text-white">Push allowed</div>
                <div className="text-[10px] text-zinc-500">Or blocked (exit 1)</div>
              </div>
            </div>

            {/* Pre-push hook code */}
            <div className="rounded-xl bg-black/40 border border-white/[0.06] p-5 font-mono text-[11px] leading-relaxed mb-6">
              <div className="text-zinc-500 mb-2"># .git/hooks/pre-push (installed by zephyr init-githooks)</div>
              <div className="text-blue-400">echo</div> <span className="text-emerald-400">&quot;📦 Generating SBOF digest...&quot;</span><br/>
              <span className="text-amber-400">zephyr digest</span> --output .zephyrci/digest.json<br/><br/>
              <div className="text-blue-400">echo</div> <span className="text-emerald-400">&quot;📦 Exporting SBOF bundle...&quot;</span><br/>
              <span className="text-amber-400">zephyr sbof-export</span> --digest .zephyrci/digest.json --out .zephyrci/sbof.json<br/><br/>
              <div className="text-blue-400">echo</div> <span className="text-emerald-400">&quot;🛡️ Running Zephyr gatekeeper...&quot;</span><br/>
              <span className="text-amber-400">zephyr gatekeeper</span> --input .zephyrci/sbof.json<br/><br/>
              <span className="text-red-400">if</span> [ $? -ne 0 ]; <span className="text-red-400">then</span><br/>
              <span className="pl-4 text-red-400">echo</span> <span className="text-red-300">&quot;❌ Gatekeeper failed. Push aborted.&quot;</span><br/>
              <span className="pl-4 text-red-400">exit 1</span><br/>
              <span className="text-red-400">fi</span>
            </div>

            {/* Trust policy */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="rounded-xl bg-black/40 border border-white/[0.06] p-5">
                <div className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-2">
                  <Lock className="w-3.5 h-3.5 text-amber-500" />
                  Trust Policy
                  <span className="text-[10px] text-zinc-600 font-normal">~/.zephyr/trust-policy.yml</span>
                </div>
                <div className="font-mono text-[11px] leading-relaxed">
                  <div className="text-amber-400">allowed_signers:</div>
                  <div className="text-emerald-400 pl-4">- 1/QL5bc6bfAIWy3uJ1KYE...</div>
                  <div className="text-zinc-600 pl-4"># ↑ your machine&apos;s public key</div>
                </div>
              </div>

              <div className="rounded-xl bg-black/40 border border-white/[0.06] p-5">
                <div className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-2">
                  <Key className="w-3.5 h-3.5 text-emerald-500" />
                  Your Identity
                  <span className="text-[10px] text-zinc-600 font-normal">zephyr whoami</span>
                </div>
                <div className="font-mono text-[11px] leading-relaxed">
                  <div className="text-zinc-500">🪪 Zephyr Identity:</div>
                  <div className="text-emerald-400 pl-4">🔑 1/QL5bc6bfAIWy3uJ1KYE...</div>
                </div>
              </div>
            </div>

            {/* Pass vs Block */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  <span className="font-semibold text-emerald-400 text-sm">Key in trust policy</span>
                </div>
                <div className="font-mono text-[11px] text-zinc-400 space-y-1">
                  <div>🛡️ Running Zephyr gatekeeper...</div>
                  <div className="text-emerald-400">✅ Zephyr gatekeeper passed.</div>
                  <div className="text-emerald-400">Proceeding with push.</div>
                </div>
              </div>

              <div className="rounded-xl border border-red-500/20 bg-red-500/[0.04] p-4">
                <div className="flex items-center gap-2 mb-3">
                  <XCircle className="w-5 h-5 text-red-400" />
                  <span className="font-semibold text-red-400 text-sm">Key NOT in trust policy</span>
                </div>
                <div className="font-mono text-[11px] text-zinc-400 space-y-1">
                  <div>🛡️ Running Zephyr gatekeeper...</div>
                  <div className="text-red-400">❌ Gatekeeper failed. Push aborted.</div>
                  <div className="text-zinc-600"># git push exits with code 1</div>
                  <div className="text-zinc-600"># files stay on the machine</div>
                </div>
              </div>
            </div>

            <p className="text-sm text-zinc-400 leading-relaxed">
              <strong className="text-zinc-300">The Gatekeeper runs as a git pre-push hook.</strong> Before any push reaches the remote,
              Zephyr digests all signed artifacts, bundles them into an SBOF file, and checks each signature
              against the trust policy. If any artifact was signed by a key not in <code className="text-zinc-300 text-xs bg-white/[0.05] px-1 rounded">allowed_signers</code>,
              the push is physically blocked. The files never leave the machine.
            </p>
          </div>

          {/* Demo commands */}
          <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.03] p-6">
            <div className="text-xs font-semibold text-amber-400 uppercase tracking-widest mb-4 flex items-center gap-2">
              <Hexagon className="w-3.5 h-3.5" /> Live Demo
            </div>
            <div className="font-mono text-[12px] leading-loose space-y-4">
              <div>
                <div className="text-zinc-500"># 1. Show your signing identity</div>
                <div className="text-amber-400">$ zephyr whoami</div>
              </div>
              <div>
                <div className="text-zinc-500"># 2. Show who&apos;s authorized to push</div>
                <div className="text-amber-400">$ cat ~/.zephyr/trust-policy.yml</div>
              </div>
              <div>
                <div className="text-zinc-500"># 3. Install gatekeeper hooks</div>
                <div className="text-amber-400">$ zephyr init-githooks</div>
              </div>
              <div>
                <div className="text-zinc-500"># 4. Push — gatekeeper runs automatically</div>
                <div className="text-amber-400">$ git push origin main</div>
                <div className="text-emerald-400">✅ Zephyr gatekeeper passed. Proceeding with push.</div>
              </div>
              <div>
                <div className="text-zinc-500"># 5. Demo a block: clear the trust policy</div>
                <div className="text-amber-400">$ echo &quot;allowed_signers: []&quot; &gt; ~/.zephyr/trust-policy.yml</div>
                <div className="text-amber-400">$ git push origin main</div>
                <div className="text-red-400">❌ Gatekeeper failed. Push aborted.</div>
              </div>
              <div>
                <div className="text-zinc-500"># 6. Restore — add your key back</div>
                <div className="text-amber-400">$ echo &quot;allowed_signers:</div>
                <div className="text-amber-400">  - $(zephyr pubkey)&quot; &gt; ~/.zephyr/trust-policy.yml</div>
              </div>
            </div>
          </div>
        </section>

        {/* How Honeymoon Uses Zephyr */}
        <section className="mb-16">
          <h2 className="text-sm font-bold text-zinc-500 uppercase tracking-widest mb-6">How Honeymoon Uses This</h2>

          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8">
            <div className="space-y-6">
              {/* Three signing layers */}
              {[
                {
                  icon: Hexagon,
                  color: "#f59e0b",
                  title: "Pipeline Events → audit.jsonl",
                  desc: "Every agent action, tool call, plan submission, and security verdict is serialized, signed, and appended to the audit log. Zephyr hardware signing takes priority if available; Ed25519 software signing is the fallback.",
                  items: ["Agent activated: planner", "Tool executed: npm test (exit 0)", "Finding submitted: allowlist bypass", "Security verdict: warn"],
                },
                {
                  icon: FileCheck,
                  color: "#3b82f6",
                  title: "Investigation Reports → reports/*.md",
                  desc: "Every scan, simulation, and deep scan report is Ed25519 signed. The signature covers everything above the attestation separator. Anyone with the public key can verify the report is authentic and unmodified.",
                  items: ["Summary + findings + evidence", "Verification verdict", "Cost breakdown", "Attestation block with signature"],
                },
                {
                  icon: Shield,
                  color: "#10b981",
                  title: "Hardening Ledger → ledger.jsonl",
                  desc: "Every hardening run appends a signed entry to the ledger. The posture score, new/resolved findings, and severity breakdown are all covered by the signature. The ledger is append-only — you cannot retroactively insert or modify entries.",
                  items: ["Posture score: 80/100", "New findings: 2, Resolved: 5", "Trend: improving", "Signed by key 56c5...71a5"],
                },
              ].map((layer, i) => {
                const Icon = layer.icon;
                return (
                  <div key={i} className="flex gap-5">
                    <div
                      className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 mt-1"
                      style={{ background: `${layer.color}15`, border: `1px solid ${layer.color}33` }}
                    >
                      <Icon className="w-6 h-6" style={{ color: layer.color }} />
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-white mb-1">{layer.title}</div>
                      <p className="text-xs text-zinc-400 leading-relaxed mb-3">{layer.desc}</p>
                      <div className="flex flex-wrap gap-2">
                        {layer.items.map((item, j) => (
                          <span
                            key={j}
                            className="text-[10px] px-2 py-1 rounded-md font-mono"
                            style={{ background: `${layer.color}10`, color: `${layer.color}cc`, border: `1px solid ${layer.color}25` }}
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Use Cases Beyond Honeymoon */}
        <section className="mb-16">
          <h2 className="text-sm font-bold text-zinc-500 uppercase tracking-widest mb-6">Beyond Honeymoon</h2>

          <div className="grid grid-cols-2 gap-4">
            {[
              { title: "CI/CD Provenance", desc: "Sign build artifacts and deployment events. Prove which pipeline produced which artifact and that it wasn't modified between build and deploy." },
              { title: "Audit Compliance", desc: "Signed ledgers for SOC2, ISO 27001, HIPAA. Auditors verify signatures against the public key instead of trusting self-reported logs." },
              { title: "Agent Attestation", desc: "Any AI agent system can sign its actions. Prove which agent made which decision, trace the reasoning chain, and verify it wasn't fabricated." },
              { title: "Data Lineage", desc: "Sign data transformations in ML pipelines. Every preprocessing step, model training run, and evaluation result gets a tamper-evident record." },
            ].map((uc, i) => (
              <div key={i} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5">
                <div className="text-sm font-semibold text-white mb-2">{uc.title}</div>
                <p className="text-xs text-zinc-400 leading-relaxed">{uc.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Footer */}
        <footer className="pt-6 border-t border-white/[0.04] text-[11px] text-zinc-600">
          Zephyr SBOF &middot; Adjective LLC &middot; Ed25519 cryptographic attestation
        </footer>
      </div>
    </div>
  );
}
