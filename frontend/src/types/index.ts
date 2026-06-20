export interface User {
  uid: string;
  email: string;
  firstname: string;
  lastname: string;
}

export interface Notebook {
  id: string;
  name: string;
  owner_id: string;
}

export interface Note {
  id: string;
  notebook_id: string;
  owner_id: string;
  title: string;
  creation_timestamp: string;
  update_timestamp: string;
}

export type MarkdownBlockType = 'paragraph' | 'heading' | 'blockquote' | 'list_item' | 'image' | 'code_block';

export interface NoteNode {
  id: string;
  note_id: string;
  author_id: string;
  node_type: string;
  payload: string | null;
  block_type: string | null;
  version: number;
  update_timestamp: string;
}
