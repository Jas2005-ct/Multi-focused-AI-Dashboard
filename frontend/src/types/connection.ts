export interface ActiveConnection {
  id: number;
  host: string;
  database: string;
  username: string;
  tables: string[];
}
