import { useMutation, useQueryClient } from "@tanstack/react-query"
import { createDocument } from "@/api/documents"

export function useCreateDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createDocument,
    onSuccess: (document) => {
      // Seed the cache so the detail page the user is about to land on
      // renders instantly instead of a loading flash.
      queryClient.setQueryData(["document", document.id], document)
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
  })
}
