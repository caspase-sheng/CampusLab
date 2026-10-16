// 笔记页：列表 + 增删改查。契约见 docs/CONTRACT.md §4.4。
//
// 本次不对 content_md 做 Markdown 渲染：不引 marked / react-markdown 之类的库，
// 内容在 textarea 里按纯文本编辑、列表里也不渲染。预览等功能后续再加。

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { createNote, deleteNote, listNotes, updateNote } from "../api/notes";
import type { Note, NoteCreate } from "../api/types";
import { formatDateTime } from "../utils/datetime";

/** 把 "算法,KV" 这类逗号分隔串切成去空的小标签数组。 */
function parseTags(tags: string | null): string[] {
  if (tags === null) {
    return [];
  }
  return tags
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);
}

export default function Notes() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // editing 为 null 表示新建，非 null 表示正在编辑这条笔记；showForm 控制面板显隐。
  const [editing, setEditing] = useState<Note | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 表单字段。tags 用空串表示「没填」，提交时再转成 null（见 handleSubmit）。
  const [title, setTitle] = useState("");
  const [contentMd, setContentMd] = useState("");
  const [tags, setTags] = useState("");

  /** 拉一次笔记列表。页面对增删改后的刷新都复用它。 */
  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await listNotes();
      setNotes(list);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "加载笔记失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** 打开新建表单：字段回到默认值。 */
  function openCreate() {
    setEditing(null);
    setFormError(null);
    setTitle("");
    setContentMd("");
    setTags("");
    setShowForm(true);
  }

  /** 打开编辑表单：用这条笔记的现有值预填，tags 为 null 时填成空串。 */
  function openEdit(note: Note) {
    setEditing(note);
    setFormError(null);
    setTitle(note.title);
    setContentMd(note.content_md);
    setTags(note.tags ?? "");
    setShowForm(true);
  }

  /** 关闭表单并清掉编辑态。 */
  function closeForm() {
    setShowForm(false);
    setEditing(null);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const trimmedTitle = title.trim();
    if (trimmedTitle === "") {
      setFormError("标题不能为空");
      return;
    }
    // 内容里的换行有意义，只 trim 首尾空白再判空，别把中间的空行也顺手删了。
    if (contentMd.trim() === "") {
      setFormError("内容不能为空");
      return;
    }

    // tags 空串转成 null 再发：传 "" 会在库里存个空串，编辑时清空标签读回来是 ""，
    // 而不是「这个字段没有值」；传 null 才是真正的「清空」。
    const payload: NoteCreate = {
      title: trimmedTitle,
      content_md: contentMd,
      tags: tags.trim() === "" ? null : tags.trim(),
    };

    setSubmitting(true);
    try {
      if (editing !== null) {
        await updateNote(editing.id, payload);
      } else {
        await createNote(payload);
      }
      closeForm();
      // 保存成功后重新拉列表最省事，不用在本地手动拼一份新的 notes。
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "保存失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (editing === null) {
      return;
    }
    if (!window.confirm("确定删除这条笔记？")) {
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await deleteNote(editing.id);
      closeForm();
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "删除失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">笔记</h1>
        <button
          type="button"
          onClick={openCreate}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white transition-colors hover:bg-slate-700"
        >
          新建笔记
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-5"
        >
          <h2 className="text-lg font-medium text-slate-900">
            {editing !== null ? "编辑笔记" : "新建笔记"}
          </h2>

          {formError !== null && (
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
              {formError}
            </p>
          )}

          <div>
            <label className="mb-1 block text-sm text-slate-600" htmlFor="note-title">
              标题
            </label>
            <input
              id="note-title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-600" htmlFor="note-content">
              内容
            </label>
            <textarea
              id="note-content"
              required
              rows={12}
              value={contentMd}
              onChange={(e) => setContentMd(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm outline-none focus:border-slate-500"
            />
            <p className="mt-1 text-xs text-slate-500">
              本次先按纯文本编辑，Markdown 预览后续再加
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-600" htmlFor="note-tags">
              标签
            </label>
            <input
              id="note-tags"
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="逗号分隔，如 算法,KV"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "保存中…" : "保存"}
            </button>
            <button
              type="button"
              onClick={closeForm}
              disabled={submitting}
              className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              取消
            </button>

            {editing !== null && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={submitting}
                className="ml-auto rounded bg-red-600 px-4 py-2 text-sm text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                删除
              </button>
            )}
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-slate-500">加载中…</p>
      ) : loadError !== null ? (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
          {loadError}
        </p>
      ) : notes.length === 0 ? (
        <p className="text-sm text-slate-500">还没有笔记，点右上角新建一条</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {notes.map((note) => {
            const tagList = parseTags(note.tags);
            return (
              <li key={note.id}>
                <button
                  type="button"
                  onClick={() => openEdit(note)}
                  className="block w-full px-4 py-3 text-left transition-colors hover:bg-slate-50"
                >
                  <div className="truncate font-medium text-slate-900">
                    {note.title}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {tagList.map((tag, index) => (
                      <span
                        key={`${tag}-${index}`}
                        className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                      >
                        {tag}
                      </span>
                    ))}
                    <span className="text-xs text-slate-400">
                      更新于 {formatDateTime(note.updated_at)}
                    </span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
