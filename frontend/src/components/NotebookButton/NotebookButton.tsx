import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createNotebook } from "../../services/api";
import "./NotebookButton.css";

interface NotebookButtonProps {
  onNotebookCreated?: (id: number) => void;
}

export const NotebookButton = ({ onNotebookCreated }: NotebookButtonProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (title?: string) => createNotebook(title),
    retry: false,
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["notebooks"] });
      if (response?.id) {
        if (onNotebookCreated) {
          onNotebookCreated(response.id);
        }
        navigate(`/notebooks/${response.id}`);
      } else {
        console.warn("createNotebook response missing id:", response);
      }
    },
    onError: (error) => {
      console.error("Error creating notebook:", error);
    },
  });

  const handleCreateClick = () => {
    const placeholder = t("notebook_title_placeholder");
    const input = window.prompt(placeholder, "");
    if (input === null) return; // user cancelled
    const title = input.trim() || placeholder;
    createMutation.mutate(title);
  };

  return (
    <button
      className="notebook-button"
      onClick={handleCreateClick}
      disabled={createMutation.isPending}
      title={t("create_notebook")}
    >
      ➕ {createMutation.isPending ? t("creating") : t("create_notebook")}
    </button>
  );
};
