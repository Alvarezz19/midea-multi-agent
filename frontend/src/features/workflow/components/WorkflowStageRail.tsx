import type { AttemptDetail } from "../../../types/workflow";
import { WORKFLOW_STAGES, getStageIndex } from "../lib/currentStepMapping";

interface WorkflowStageRailProps {
  attempt: AttemptDetail;
}

export function WorkflowStageRail({ attempt }: WorkflowStageRailProps) {
  const activeIndex = getStageIndex(attempt.current_step, attempt.status);

  return (
    <section className="panel stage-panel">
      <div className="panel-heading">
        <p className="eyebrow">Stage Rail</p>
        <h2>主阶段轨道</h2>
        <p>只表达当前主阶段，不按固定节点数量承诺百分比进度。</p>
      </div>
      <ol className="stage-rail">
        {WORKFLOW_STAGES.map((stage, index) => {
          const isActive = index === activeIndex;
          const isDone = activeIndex >= 0 && index < activeIndex;
          return (
            <li className={isActive ? "active" : isDone ? "done" : ""} key={stage.key}>
              <span className="stage-marker">{index + 1}</span>
              <div>
                <strong>{stage.label}</strong>
                <small>{stage.description}</small>
              </div>
            </li>
          );
        })}
      </ol>
      {activeIndex === -1 ? (
        <p className="unknown-step">未知阶段：{attempt.current_step || "空 current_step"}</p>
      ) : null}
    </section>
  );
}
