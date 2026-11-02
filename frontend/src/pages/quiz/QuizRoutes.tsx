import { Route, Routes } from "react-router-dom";
import QuizSetup from "./QuizSetup";
import QuizBuild from "./QuizBuild";
import QuizTake from "./QuizTake";
import QuizReview from "./QuizReview";
import QuizResultsPage from "./QuizResults";

export default function QuizRoutes() {
  return (
    <Routes>
      <Route index element={<QuizSetup />} />
      <Route path="build/:jobId" element={<QuizBuild />} />
      <Route path=":id" element={<QuizTake />} />
      <Route path=":id/review" element={<QuizReview />} />
      <Route path=":id/results" element={<QuizResultsPage />} />
    </Routes>
  );
}
