import { sqliteTable, text } from 'drizzle-orm/sqlite-core';
export const reviewState = sqliteTable('review_state', {
 id: text('id').primaryKey(),
 status: text('status').notNull(),
 note: text('note').notNull().default(''),
 updatedAt: text('updated_at').notNull(),
});
