"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { VideoIcon } from "lucide-react";

import { useSession } from "@/components/auth/session-context";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FormErrors {
  displayName?: string;
  email?: string;
  password?: string;
}

export default function RegisterPage() {
  const router = useRouter();
  const { status, register } = useSession();

  const [displayName, setDisplayName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [errors, setErrors] = React.useState<FormErrors>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  React.useEffect(() => {
    if (status === "authenticated") {
      router.replace("/");
    }
  }, [status, router]);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedName = displayName.trim();
    const trimmedEmail = email.trim();
    const nextErrors: FormErrors = {};
    if (!trimmedName) {
      nextErrors.displayName = "Enter your name.";
    }
    if (!trimmedEmail) {
      nextErrors.email = "Enter your email.";
    } else if (!EMAIL_PATTERN.test(trimmedEmail)) {
      nextErrors.email = "Enter a valid email address.";
    }
    if (!password) {
      nextErrors.password = "Enter a password.";
    } else if (password.length < 8) {
      nextErrors.password = "Password must be at least 8 characters.";
    }
    setErrors(nextErrors);
    setFormError(null);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    setPending(true);
    try {
      await register({ email: trimmedEmail, password, displayName: trimmedName });
      router.replace("/");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Something went wrong. Try again.");
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <Link
          href="/"
          aria-label="Procto home"
          className="mb-6 flex items-center justify-center gap-2"
        >
          <span
            aria-hidden="true"
            className="bg-primary text-primary-foreground flex size-10 items-center justify-center rounded-xl"
          >
            <VideoIcon />
          </span>
          <span className="font-heading text-xl font-semibold tracking-tight">Procto</span>
        </Link>

        <Card>
          <CardHeader>
            <CardTitle>Create your account</CardTitle>
            <CardDescription>Set up your Procto profile in a few seconds.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
              {formError && (
                <Alert variant="destructive">
                  <AlertDescription>{formError}</AlertDescription>
                </Alert>
              )}

              <Field data-invalid={errors.displayName ? "true" : undefined}>
                <FieldLabel htmlFor="display-name">Name</FieldLabel>
                <Input
                  id="display-name"
                  type="text"
                  autoComplete="name"
                  placeholder="Hasan"
                  value={displayName}
                  disabled={pending}
                  aria-invalid={errors.displayName ? true : undefined}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
                {errors.displayName && <FieldError>{errors.displayName}</FieldError>}
              </Field>

              <Field data-invalid={errors.email ? "true" : undefined}>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  disabled={pending}
                  aria-invalid={errors.email ? true : undefined}
                  onChange={(event) => setEmail(event.target.value)}
                />
                {errors.email && <FieldError>{errors.email}</FieldError>}
              </Field>

              <Field data-invalid={errors.password ? "true" : undefined}>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="••••••••"
                  value={password}
                  disabled={pending}
                  aria-invalid={errors.password ? true : undefined}
                  onChange={(event) => setPassword(event.target.value)}
                />
                {errors.password ? (
                  <FieldError>{errors.password}</FieldError>
                ) : (
                  <FieldDescription>At least 8 characters.</FieldDescription>
                )}
              </Field>

              <Button type="submit" className="w-full" disabled={pending}>
                {pending && <Spinner data-icon="inline-start" />}
                Create account
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="text-muted-foreground mt-4 text-center text-sm">
          Already have an account?{" "}
          <Link href="/login" className="text-primary font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
