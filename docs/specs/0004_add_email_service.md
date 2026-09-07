## Add email service

We are introducing a service to send email messages to our users via Mailgun.
The key of this spec is the abstraction to allow product features to send
mail.

## Integration

We use Mailgun as our email sending service.

- We are going to use Mailgun API rather than SMTP to send the email.
  [API doc](https://documentation.mailgun.com/docs/mailgun/api-reference/send/mailgun/messages/post-v3--domain-name--messages)

- The API key and the mailgun server are accessed via config.py. We are going
  to add a TypedDict in [config.py](../../src/assistant/config.py).

- The typedcdict contains two entries: mailgun api URL and mailgun api key.

- The api kay will always be provided via environment variable.

- We add a email.py service that has a `send_email` method that takes anm Email
  object

## Email objects and templates

- The client can send an email by creating an Email object that references:
  a recipient, a template, values for the template.

- The template engine we use is string.Template for now.

- We store templates in a separate module.

## Sending email

- We use the requests package to send email with the `post` method.

- We do not support any email mime type beyond text as of now.
