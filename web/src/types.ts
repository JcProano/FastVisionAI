export interface DashboardPayload {
  available: boolean;
  camera: string;
  camera_name?: string;
  camera_type?: string;
  recognition: string;
  database: string;
  attendance: string;
  gallery: number;
  people_summary: {
    registered_people: number;
    biometric_identities: number;
    without_face: number;
  };
  statistics: {
    people_present: number | null;
    recognitions_today: number | null;
    check_ins_today: number | null;
    late_today: number | null;
  };
  recent_recognitions: Array<{
    photo: string | null;
    name: string;
    time: string;
    similarity: number | null;
    state: string;
  }>;
  recent_attendance: Array<{
    photo: string | null;
    name: string;
    check_in: string | null;
    check_out: string | null;
    status: string;
  }>;
}

export interface PresentationPayload {
  active: boolean;
  kind: string;
  title: string;
  status: string;
  name?: string | null;
  photo?: string | null;
  similarity?: number | null;
  warning?: string | null;
  details?: Array<{ label: string; value: string }>;
}

export interface EnrollmentStatus {
  active: boolean;
  stage: string;
  accepted_samples: number;
  target_samples: number;
  instruction: string | null;
  quality_score: number | null;
  quality_band: string | null;
  can_continue: boolean;
  summary: Record<string, string>;
  success?: boolean;
}

export interface CameraDTO {
  id: string;
  name: string;
  type: string;
  status: string;
  available: boolean;
  preferred: boolean;
  active: boolean;
  network: boolean;
}

export interface PersonDTO {
  token: string;
  name: string;
  first_name: string;
  last_name: string;
  cedula: string;
  phone?: string | null;
  email?: string | null;
  status: string;
  biometrics: string;
  thumbnail?: string | null;
}
