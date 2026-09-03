import { createBrowserRouter } from "react-router-dom"
import { RootLayout } from "@/routes/RootLayout"
import { DocumentListPage } from "@/routes/DocumentListPage"
import { NewDocumentPage } from "@/routes/NewDocumentPage"
import { DocumentDetailPage } from "@/routes/DocumentDetailPage"

// A future /login route (unauthenticated) sits as a sibling outside
// RootLayout's element; RootLayout itself gains the auth-guard wrapper
// mentioned in its own file once auth exists.
export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      { index: true, element: <DocumentListPage /> },
      { path: "documents/new", element: <NewDocumentPage /> },
      { path: "documents/:id", element: <DocumentDetailPage /> },
    ],
  },
])
