// Every URL in the app lives here, so a route only ever changes in one place.
export const ROUTES = {
  home: "/",
  verify: (id: string) => `/verify/${id}`,
  login: (next?: string) => (next ? `/login?next=${encodeURIComponent(next)}` : "/login"),
  signup: (next?: string) => (next ? `/?next=${encodeURIComponent(next)}` : "/"),
  tutor: {
    home: "/tutor",
    landing: "/tutor",
    login: "/login",
    signup: "/?role=teacher",
    createProfile: "/tutor/create-profile",
    dashboard: "/tutor/dashboard",
    requests: "/tutor/requests",
    request: (userId: string, requestId: string) =>
      `/tutor/requests/${encodeURIComponent(userId)}/${encodeURIComponent(requestId)}`,
    students: "/tutor/students",
    student: (userId: string) => `/tutor/students/${encodeURIComponent(userId)}`,
    schedule: "/tutor/schedule",
    live: "/meet?as=tutor", // Neural Hub Institute Meet (full screen)
    reviews: "/tutor/reviews",
    lectures: "/tutor/lectures",
    newLecture: "/tutor/lectures/new",
    lecture: (id: string) => `/tutor/lectures/${encodeURIComponent(id)}`,
    /** My lectures → Courses: the tutor's free / paid video courses. */
    videoCourses: "/tutor/lectures?view=courses",
    videoCourse: (id: string) => `/tutor/lectures/courses/${encodeURIComponent(id)}`,
    /** AI Assistant: the tutor's courses (made with AI, from their files, or written by them). */
    assistant: "/tutor/assistant",
    newCourse: (source: "ai" | "files" | "manual" = "ai") => `/tutor/assistant/new?source=${source}`,
    course: (id: string, lecture?: number) =>
      `/tutor/assistant/${encodeURIComponent(id)}${lecture ? `?lecture=${lecture}` : ""}`,
    earnings: "/tutor/earnings",
    /** Certificate requests from students of live courses (recommend / not yet / reject). */
    certificates: "/tutor/certificates",
    certificateRequest: (id: string) => `/tutor/certificates/${encodeURIComponent(id)}`,
    messages: "/tutor/messages",
    messagesWith: (userId: string) => `/tutor/messages?student=${encodeURIComponent(userId)}`,
    reports: "/tutor/reports",
    reportsFor: (userId: string) => `/tutor/reports?student=${encodeURIComponent(userId)}#progress-reports`,
    settings: "/tutor/settings",
    support: "/tutor/support",
  },
  student: {
    onboarding: "/student/onboarding",
    dashboard: "/student/dashboard",
    tutors: "/student/tutors",
    tutor: (id: string) => `/student/tutors/${id}`,
    lectures: "/student/lectures",
    lecture: (id: string) => `/student/lectures/${encodeURIComponent(id)}`,
    /** A video course the student bought / joined (or a free one). */
    videoCourse: (id: string, video?: string) =>
      `/student/courses/video/${encodeURIComponent(id)}${video ? `?v=${encodeURIComponent(video)}` : ""}`,
    requests: "/student/requests",
    courses: "/student/courses",
    ask: "/student/ask",
    /** A course made by a teacher (AI Assistant). */
    teacherCourse: (id: string, lecture?: number) =>
      `/student/courses/teacher/${encodeURIComponent(id)}${lecture !== undefined ? `?lecture=${lecture}` : ""}`,
    /** Ask a teacher for a course on this topic (Find Tutors, topic filled in). */
    requestTopic: (topic: string) => `/student/tutors?${new URLSearchParams({ topic }).toString()}`,
    course: (id: string, day?: number) => `/student/courses/${id}${day !== undefined ? `?day=${day}` : ""}`,
    /** The AI Teacher (sidebar): pick a course to learn with the avatar teacher. */
    aiTeacher: "/student/ai-teacher",
    /** The AI Teacher teaching one course. */
    aiProfessor: (studySetId: string) => `/student/ai-professor/${encodeURIComponent(studySetId)}`,
    assessments: "/student/assessments",
    progress: "/student/progress",
    sessions: "/student/sessions",
    live: "/meet?as=student", // Neural Hub Institute Meet (full screen)
    messages: "/student/messages",
    messagesWith: (tutorId: string) => `/student/messages?tutor=${encodeURIComponent(tutorId)}`,
    certificates: "/student/certificates",
    payments: "/student/payments",
    certificate: (id: string) => `/student/certificates/${id}`,
    settings: "/student/settings",
    support: "/student/support",
  },
} as const;
