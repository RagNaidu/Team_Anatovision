import { Route, Routes } from "react-router-dom";
import Overview from "./Overview";
import ReviewQueue from "./ReviewQueue";
import Questions from "./Questions";
import Access from "./Access";
import PreviewPicker from "./PreviewPicker";
import WebQuizzes from "./WebQuizzes";
import Notes from "./Notes";
import NoteDetailPage from "./NoteDetail";
import QuestionBank from "./QuestionBank";
import QuestionEditor from "./QuestionEditor";

export default function AdminRoutes() {
  return (
    <Routes>
      <Route index element={<Overview />} />
      <Route path="review" element={<ReviewQueue />} />
      <Route path="notes" element={<Notes />} />
      <Route path="notes/:docId" element={<NoteDetailPage />} />
      <Route path="bank" element={<QuestionBank />} />
      <Route path="bank/:qid" element={<QuestionEditor />} />
      <Route path="questions" element={<Questions />} />
      <Route path="web-quizzes" element={<WebQuizzes />} />
      <Route path="access" element={<Access />} />
      <Route path="preview" element={<PreviewPicker />} />
    </Routes>
  );
}
