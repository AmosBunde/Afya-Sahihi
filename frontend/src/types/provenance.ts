export interface BoundingBox {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_title: string;
  section_path: readonly string[];
  bounding_box: BoundingBox;
  similarity_score: number;
}
