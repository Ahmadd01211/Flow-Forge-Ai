import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  GitBranch,
  Play,
  ShieldCheck,
  Sparkles,
  Workflow,
  Zap,
} from "lucide-react";
import { Brand } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";

export default function Landing() {
  return (
    <div className="landing">
      <nav className="marketing-nav">
        <Link href="/">
          <Brand />
        </Link>
        <div className="marketing-links">
          <a href="#how-it-works">How it works</a>
          <a href="#control">Built for control</a>
          <a href="/api/docs">
            API reference <ArrowUpRight size={13} />
          </a>
        </div>
        <div className="row">
          <Link href="/login" className="nav-login">
            Sign in
          </Link>
          <Button asChild size="sm">
            <Link href="/register">
              Start building <ArrowRight size={15} />
            </Link>
          </Button>
        </div>
      </nav>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <div className="hero-label">
              <span /> THE WORKSPACE FOR AI AUTOMATION
            </div>
            <h1>
              From intelligent
              <br />
              agents to
              <br />
              <span>work that flows.</span>
            </h1>
            <p>
              Build your agents. Connect your logic. Turn complex processes into
              workflows you can understand and control.
            </p>
            <div className="row hero-actions">
              <Button asChild>
                <Link href="/register">
                  Create your workspace <ArrowRight size={17} />
                </Link>
              </Button>
              <Button asChild variant="outline">
                <a href="#how-it-works">
                  <Play size={15} /> Explore the builder
                </a>
              </Button>
            </div>
            <div className="hero-foot">
              <ShieldCheck size={15} /> Explicit permissions <span>·</span>{" "}
              Bounded execution <span>·</span> Visible outcomes
            </div>
          </div>
          <div
            className="hero-visual"
            aria-label="Illustrative support triage workflow"
          >
            <div className="visual-toolbar">
              <span>
                <Workflow size={15} /> Support ticket triage
              </span>
              <span className="sample-tag">ILLUSTRATIVE WORKFLOW</span>
            </div>
            <div className="visual-canvas">
              <svg viewBox="0 0 600 470" aria-hidden="true">
                <path d="M130 115 H225 Q245 115 245 145 V185 H300 M300 245 V300 M300 300 H135 V355 M300 300 H460 V355" />
              </svg>
              <div className="preview-node trigger">
                <span className="node-icon teal">
                  <Zap size={19} />
                </span>
                <div>
                  <small>TRIGGER</small>
                  <strong>New support ticket</strong>
                  <p>Structured ticket input</p>
                </div>
              </div>
              <div className="preview-node intelligence">
                <span className="node-icon purple">
                  <Bot size={21} />
                </span>
                <div>
                  <small>AI AGENT</small>
                  <strong>Understand & classify</strong>
                  <p>Priority · intent · next step</p>
                </div>
                <span className="mini-label">8 turn cap</span>
              </div>
              <div className="branch-label">
                <GitBranch size={15} /> Route by priority
              </div>
              <div className="preview-node result-one">
                <span className="node-icon amber">
                  <GitBranch size={18} />
                </span>
                <div>
                  <small>URGENT</small>
                  <strong>Escalation summary</strong>
                </div>
              </div>
              <div className="preview-node result-two">
                <span className="node-icon blue">
                  <Check size={19} />
                </span>
                <div>
                  <small>STANDARD</small>
                  <strong>Suggested response</strong>
                </div>
              </div>
            </div>
            <div className="visual-footer">
              <span>
                <ShieldCheck size={13} /> Read-only tools
              </span>
              <span>
                60s timeout <span>·</span> $0.10 budget cap
              </span>
            </div>
          </div>
        </section>
        <section id="how-it-works" className="marketing-section">
          <div className="section-intro">
            <div className="eyebrow">BUILD WITH INTENT</div>
            <h2>
              Your logic. Your agents.
              <br />
              One connected workspace.
            </h2>
            <p>
              A clear path from the first instruction to an inspectable
              workflow.
            </p>
          </div>
          <div className="feature-grid">
            {[
              {
                icon: Bot,
                n: "01",
                title: "Give your agent a purpose",
                body: "Define instructions, structured inputs and outputs, and clear resource limits.",
              },
              {
                icon: Workflow,
                n: "02",
                title: "Connect the moving parts",
                body: "Bring agents, conditions and transformations together on a visual canvas.",
              },
              {
                icon: ShieldCheck,
                n: "03",
                title: "Keep execution accountable",
                body: "Design for explicit tool permissions, immutable versions and traceable outcomes.",
              },
            ].map((f) => (
              <article key={f.n}>
                <div className="feature-top">
                  <f.icon size={23} />
                  <span>{f.n}</span>
                </div>
                <h3>{f.title}</h3>
                <p>{f.body}</p>
              </article>
            ))}
          </div>
        </section>
        <section id="control" className="control-section">
          <div>
            <Sparkles size={27} />
            <h2>
              Power is useful.
              <br />
              Control makes it dependable.
            </h2>
            <p>
              See the instructions, permissions and limits behind every agent.
              The platform is being built in tested slices, with live execution
              capabilities introduced as they are verified.
            </p>
            <Button asChild variant="outline">
              <Link href="/register">
                Build your first draft <ArrowRight size={16} />
              </Link>
            </Button>
          </div>
          <div className="policy-card">
            <div className="row">
              <ShieldCheck size={19} />
              <strong>Execution policy</strong>
              <span className="sample-tag">DESIGN EXAMPLE</span>
            </div>
            {[
              ["Maximum iterations", "8 turns"],
              ["Execution deadline", "60 seconds"],
              ["Maximum spend", "$0.10 / run"],
              ["Tool access", "Explicitly granted"],
              ["Version resolution", "Immutable snapshot"],
            ].map(([label, value]) => (
              <div className="policy-line" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="marketing-cta">
          <div className="eyebrow">LESS FRICTION. MORE FLOW.</div>
          <h2>Build the way your work works.</h2>
          <Button asChild>
            <Link href="/register">
              Get started with FlowForge <ArrowRight size={17} />
            </Link>
          </Button>
        </section>
      </main>
      <footer className="marketing-footer">
        <Brand />
        <span>Agents with purpose. Workflows with clarity.</span>
        <Link href="/login">
          Open workspace <ArrowUpRight size={15} />
        </Link>
      </footer>
    </div>
  );
}
