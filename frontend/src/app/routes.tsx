import { Navigate, createBrowserRouter } from "react-router-dom";

import { WorkflowDebugPage } from "../features/workflow/pages/WorkflowDebugPage";
import { WorkflowHomePage } from "../features/workflow/pages/WorkflowHomePage";
import { WorkflowResultPage } from "../features/workflow/pages/WorkflowResultPage";
import { WorkflowRunPage } from "../features/workflow/pages/WorkflowRunPage";

function RouteErrorPage() {
  return (
    <main className="route-error">
      <p className="eyebrow">Route Error</p>
      <h1>页面暂时无法打开</h1>
      <p>请回到工作流首页重新进入当前 thread / attempt。</p>
      <a className="button-like" href="/workflow">
        返回工作流首页
      </a>
    </main>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Navigate to="/workflow" replace />
  },
  {
    path: "/workflow",
    element: <WorkflowHomePage />,
    errorElement: <RouteErrorPage />
  },
  {
    path: "/workflow/:threadId/:attemptId",
    element: <WorkflowRunPage />,
    errorElement: <RouteErrorPage />
  },
  {
    path: "/workflow/:threadId/:attemptId/result",
    element: <WorkflowResultPage />,
    errorElement: <RouteErrorPage />
  },
  {
    path: "/workflow/:threadId/:attemptId/debug",
    element: <WorkflowDebugPage />,
    errorElement: <RouteErrorPage />
  },
  {
    path: "*",
    element: <Navigate to="/workflow" replace />
  }
]);
