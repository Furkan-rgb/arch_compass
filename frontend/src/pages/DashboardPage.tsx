import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpenCheck,
  Boxes,
  CircleCheck,
  Clock3,
  Compass,
  FileSearch,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../api";
import {
  Badge,
  EmptyState,
  ErrorPanel,
  Loading,
  PageHeader,
  Stat,
  formatDate,
  shortId,
} from "../components";

export function DashboardPage() {
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });

  if (workspace.isLoading || cases.isLoading || repositories.isLoading || reviews.isLoading) {
    return <Loading />;
  }
  const error = workspace.error || cases.error || repositories.error || reviews.error;
  if (error) return <ErrorPanel error={error} />;

  const recentCases = cases.data?.slice(0, 4) || [];

  return (
    <div className="page">
      <PageHeader
        eyebrow="Local architecture workspace"
        title="Find the next sound decision."
        description="Frame the case, inspect bounded evidence, and keep the recommendation traceable."
        action={
          <Link to="/reviews" className="button button--primary">
            <Sparkles size={17} />
            Review a repository
          </Link>
        }
      />

      <section className="hero-grid">
        <article className="hero-card hero-card--primary">
          <div className="hero-card__compass"><Compass size={46} strokeWidth={1.3} /></div>
          <span className="eyebrow eyebrow--light">Architecture fieldwork</span>
          <h2>Point Arch Compass at a decision—not merely a codebase.</h2>
          <p>
            Use a repository when structure matters, or stay greenfield when the
            evidence is still requirements, constraints, and credible future change.
          </p>
          <Link to="/new" className="text-link text-link--light">
            Frame a new case <ArrowRight size={16} />
          </Link>
        </article>

        <article className="hero-card hero-card--paper">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Workspace readiness</span>
              <h2>Ready for local analysis</h2>
            </div>
            <CircleCheck className="success-icon" size={26} />
          </div>
          <div className="readiness-list">
            <div>
              <span>Reasoning model</span>
              <strong>{workspace.data?.models.reasoning.model}</strong>
            </div>
            <div>
              <span>Embedding model</span>
              <strong>{workspace.data?.models.embedding.model}</strong>
            </div>
            <div>
              <span>Policy index</span>
              <strong>{workspace.data?.policy_index ? "Prepared" : "Built on first run"}</strong>
            </div>
          </div>
        </article>
      </section>

      <section className="stats-grid" aria-label="Workspace totals">
        <Stat label="Architecture cases" value={cases.data?.length || 0} detail="immutable revisions" />
        <Stat label="Indexed snapshots" value={repositories.data?.length || 0} detail="freshness checked at use" />
        <Stat label="Reviews" value={reviews.data?.length || 0} detail="boundaries judged against a case" />
        <Stat
          label="Policies"
          value={workspace.data?.policy_index ? "indexed" : "—"}
          detail="presented whole with every boundary"
        />
      </section>


      <section className="dashboard-columns">
        <div className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Recent cases</span>
              <h2>Decision notebook</h2>
            </div>
            <Link to="/cases" className="text-link">View all <ArrowRight size={15} /></Link>
          </div>
          {recentCases.length ? (
            <div className="item-list">
              {recentCases.map((item) => (
                <article className="case-row" key={item.case_id}>
                  <span className="case-row__icon"><FileSearch size={18} /></span>
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.current_recommendation?.summary || item.problem_statement}</p>
                    <small>Revision {item.revision} · {formatDate(item.updated_at)}</small>
                  </div>
                  {item.current_recommendation?.disposition && (
                    <Badge tone="teal">
                      {item.current_recommendation.disposition.replaceAll("_", " ")}
                    </Badge>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<BookOpenCheck size={28} />}
              title="Your decision notebook is empty"
              description="Start with a guided case or import an existing case YAML file."
              action={<Link to="/new" className="button button--secondary">Create first case</Link>}
            />
          )}
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Repository atlas</span>
              <h2>Recent evidence</h2>
            </div>
            <Link to="/repositories" className="text-link">Manage <ArrowRight size={15} /></Link>
          </div>
          {repositories.data?.length ? (
            <div className="repository-mini-list">
              {repositories.data.slice(0, 4).map((repository) => (
                <div key={repository.version_id}>
                  <span className="repo-glyph"><Boxes size={17} /></span>
                  <div>
                    <strong>{repository.root_path.split("/").at(-1)}</strong>
                    <small>{repository.node_count} nodes · {repository.edge_count} relations</small>
                  </div>
                  <span title={formatDate(repository.created_at)}><Clock3 size={15} /></span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Boxes size={28} />}
              title="No repository atlas yet"
              description="Index a Python project once, then Arch Compass will freshness-check it before use."
              action={<Link to="/repositories" className="button button--secondary">Index repository</Link>}
            />
          )}
        </div>
      </section>
    </div>
  );
}
