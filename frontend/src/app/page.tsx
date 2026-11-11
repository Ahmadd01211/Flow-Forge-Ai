import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  BookOpen,
  Check,
  GitBranch,
  Layers,
  Play,
  Plug,
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
              <span /> YOUR FIRST AUTOMATION STARTS WITH A TASK
            </div>
            <h1>
              Describe the task.
              <br />
              <span>Make it flow.</span>
            </h1>
            <p>
              Turn a familiar job into an agent or workflow. Choose a recipe,
              review its setup, and try sample input with clear permissions and
              run limits.
            </p>
            <ol className="hero-steps">
              <li>
                <span>01</span> Describe your task
              </li>
              <li>
                <span>02</span> Configure a recipe
              </li>
              <li>
                <span>03</span> Test with clear controls
              </li>
            </ol>
            <div className="row hero-actions">
              <Button asChild>
                <Link href="/register">
                  Create your workspace <ArrowRight size={17} />
                </Link>
              </Button>
              <Button asChild variant="outline">
                <a href="#product-demo">
                  <Play size={15} /> See the product demo
                </a>
              </Button>
            </div>
            <div className="hero-foot">
              <ShieldCheck size={15} /> Review setup. Test a sample. Publish
              when ready.
            </div>
          </div>
          <div
            className="hero-visual"
            id="product-demo"
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
                  <small>SAMPLE INPUT</small>
                  <strong>A support ticket</strong>
                  <p>Describe the issue and context</p>
                </div>
              </div>
              <div className="preview-node intelligence">
                <span className="node-icon purple">
                  <Bot size={21} />
                </span>
                <div>
                  <small>CONFIGURED AGENT</small>
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
                <ShieldCheck size={13} /> Policy-controlled tools
              </span>
              <span>
                60s timeout <span>·</span> $0.10 budget cap
              </span>
            </div>
            <p className="demo-caption">
              Example configuration and outputs. This illustration does not run
              a model or take live actions.
            </p>
          </div>
        </section>
        <section id="how-it-works" className="marketing-section">
          <div className="section-intro">
            <div className="eyebrow">FROM A TASK TO A TESTABLE DRAFT</div>
            <h2>
              Start with a recipe.
              <br />
              Make every step your own.
            </h2>
            <p>
              Review the expected result and setup before creating a draft. Keep
              the full editors within reach as your process grows.
            </p>
          </div>
          <div className="feature-grid">
            {[
              {
                icon: Bot,
                n: "01",
                title: "Agents with a clear purpose",
                body: "Set instructions, choose a model, and define inputs, outputs, approved tools and run limits. Readiness checks show what needs attention before publication.",
              },
              {
                icon: Workflow,
                n: "02",
                title: "Workflows you can inspect",
                body: "Connect agents, conditions, transformations and result steps on a visual canvas. Inspect validation and execution traces as you build and run.",
              },
              {
                icon: Layers,
                n: "03",
                title: "Templates for familiar tasks",
                body: "Preview setup notes, sample input and an expected result. Create an editable, workspace-visible draft from a recipe and adapt it to your team.",
              },
              {
                icon: Plug,
                n: "04",
                title: "Integrations with guided setup",
                body: "Verify a provider key, review available models and save a workspace default. Configure approved tools separately for the actions your task needs.",
              },
              {
                icon: BookOpen,
                n: "05",
                title: "Skills you can reuse",
                body: "Edit reusable instructions and examples. Review and publish attached skill versions before testing or publishing an agent that uses them.",
              },
              {
                icon: ShieldCheck,
                n: "06",
                title: "Approvals at the right step",
                body: "Add a human approval step to pause a published workflow for an owner or admin decision. Review tool permissions and any required action confirmations before execution.",
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
              Know what a test will do.
              <br />
              Choose when to run.
            </h2>
            <p>
              Local draft preview covers supported local steps. Publish before a
              full workflow run that includes agents, models, external services
              or pause steps. Review connections, permissions and run limits in
              the editor first.
            </p>
            <p>
              Model calls use your configured provider and may incur costs.
              Publishing a version and starting a run are separate actions.
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
              <strong>Sample agent policy</strong>
              <span className="sample-tag">CONFIGURATION EXAMPLE</span>
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
          <div className="eyebrow">ONE TASK. A CLEAR PLACE TO START.</div>
          <h2>What would you like to make easier?</h2>
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
        <Link href="/app">
          Open workspace <ArrowUpRight size={15} />
        </Link>
      </footer>
    </div>
  );
}
