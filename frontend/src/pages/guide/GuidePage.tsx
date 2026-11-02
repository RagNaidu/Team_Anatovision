import { Route, Routes } from "react-router-dom";
import GuidePicker from "./GuidePicker";
import StationView from "./StationView";

export default function GuidePage() {
  return (
    <Routes>
      <Route index element={<GuidePicker />} />
      <Route path="lecture/:id" element={<StationView kind="lecture" />} />
      <Route path="lecture/:id/:index" element={<StationView kind="lecture" />} />
      <Route path=":id" element={<StationView kind="guide" />} />
      <Route path=":id/:index" element={<StationView kind="guide" />} />
    </Routes>
  );
}
