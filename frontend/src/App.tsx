import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import { AuthProvider, useAuth } from "@/state/auth";
import { DataProvider } from "@/state/data";
import { AppShell } from "@/components/AppShell";
import Login from "@/pages/Login";
import AskPage from "@/pages/ask/AskPage";
import { Skeleton } from "@/components/ui/misc";

const GuidePage = lazy(() => import("@/pages/guide/GuidePage"));
const QuizRoutes = lazy(() => import("@/pages/quiz/QuizRoutes"));
const AdminRoutes = lazy(() => import("@/pages/admin/AdminRoutes"));

function Loading() {
  return (
    <div className="mx-auto max-w-[700px] space-y-4 p-8" aria-label="Loading">
      <Skeleton className="h-8 w-1/2" /><Skeleton className="h-4" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-2/3" />
    </div>
  );
}

function Protected() {
  const { status, user, preview } = useAuth();
  if (status === "loading") return <div className="flex h-dvh items-center justify-center bg-bone"><Loading /></div>;
  if (!user) return <Navigate to="/login" replace />;
  void preview;
  return (
    <DataProvider>
      <AppShell />
    </DataProvider>
  );
}

/** Student tools need a student, or an instructor who started a preview. Instructor screens need an instructor outside a preview. */
function StudentOnly({ children }: { children: JSX.Element }) {
  const { user, preview } = useAuth();
  if (user?.role === "instructor" && !preview) return <Navigate to="/admin" replace />;
  return children;
}
function InstructorOnly({ children }: { children: JSX.Element }) {
  const { user, preview } = useAuth();
  if (user?.role !== "instructor") return <Navigate to="/ask" replace />;
  if (preview) return <Navigate to="/ask" replace />;
  return children;
}
function Home() {
  const { user, preview } = useAuth();
  return <Navigate to={user?.role === "instructor" && !preview ? "/admin" : "/ask"} replace />;
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route element={<Protected />}>
                <Route index element={<Home />} />
                <Route path="ask" element={<StudentOnly><AskPage /></StudentOnly>} />
                <Route path="ask/:chatId" element={<StudentOnly><AskPage /></StudentOnly>} />
                <Route path="guide/*" element={<StudentOnly><GuidePage /></StudentOnly>} />
                <Route path="quiz/*" element={<StudentOnly><QuizRoutes /></StudentOnly>} />
                <Route path="admin/*" element={<InstructorOnly><AdminRoutes /></InstructorOnly>} />
                <Route path="*" element={<Home />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </MotionConfig>
  );
}
