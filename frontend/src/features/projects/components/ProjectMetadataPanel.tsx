import type { ProjectDetail } from "@/types/api";

interface ProjectMetadataPanelProps {
  project: ProjectDetail;
}

export function ProjectMetadataPanel({ project }: ProjectMetadataPanelProps) {
  return (
    <div className="project-detail-meta">
      <div className="project-detail-meta__header">
        <div>
          <h1 className="project-detail-meta__title">{project.title}</h1>
          <p className="project-detail-meta__subtitle">{project.code}</p>
        </div>
      </div>

      <div className="project-detail-meta__grid">
        <article className="project-detail-meta__card">
          <strong>Client</strong>
          <span>{project.client_name || "No client name"}</span>
        </article>
        <article className="project-detail-meta__card">
          <strong>Status</strong>
          <span>{project.status}</span>
        </article>
        <article className="project-detail-meta__card">
          <strong>XML standard</strong>
          <span>{project.xml_standard}</span>
        </article>
        <article className="project-detail-meta__card">
          <strong>Chapter count</strong>
          <span>{project.chapter_count}</span>
        </article>
        <article className="project-detail-meta__card">
          <strong>File count</strong>
          <span>{project.file_count}</span>
        </article>
      </div>
    </div>
  );
}
