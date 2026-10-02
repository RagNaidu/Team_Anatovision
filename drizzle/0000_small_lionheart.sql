CREATE TABLE `review_state` (
	`id` text PRIMARY KEY NOT NULL,
	`status` text NOT NULL,
	`note` text DEFAULT '' NOT NULL,
	`updated_at` text NOT NULL
);
