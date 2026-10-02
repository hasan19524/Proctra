"use client";

import * as React from "react";
import Link from "next/link";

import {
  CalendarIcon,
  CircleCheckIcon,
  HomeIcon,
  InfoIcon,
  MessageSquareIcon,
  SettingsIcon,
  TriangleAlertIcon,
  UserIcon,
  UsersIcon,
  VideoIcon,
} from "lucide-react";

import { ThemeToggle } from "@/components/theme/theme-toggle";
import { MeetingControls, UtilityCluster } from "@/components/meeting/meeting-controls";
import {
  MeetingEmptyState,
  MeetingErrorState,
  MeetingLoadingState,
} from "@/components/meeting/meeting-states";
import { MeetingTopBar } from "@/components/meeting/meeting-top-bar";
import { ChatPanel, PeoplePanel } from "@/components/meeting/meeting-panels";
import { ParticipantTile } from "@/components/meeting/participant-tile";
import { ReactionBar } from "@/components/meeting/reaction-bar";
import {
  ConnectionQuality,
  LiveIndicator,
  StatusIndicator,
} from "@/components/meeting/status-indicator";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Avatar, AvatarBadge, AvatarFallback, AvatarGroup } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "cn";

const COLOR_TOKENS: { label: string; swatch: string }[] = [
  { label: "background", swatch: "bg-background" },
  { label: "foreground", swatch: "bg-foreground" },
  { label: "card", swatch: "bg-card" },
  { label: "primary", swatch: "bg-primary" },
  { label: "primary-foreground", swatch: "bg-primary-foreground" },
  { label: "secondary", swatch: "bg-secondary" },
  { label: "muted", swatch: "bg-muted" },
  { label: "muted-foreground", swatch: "bg-muted-foreground" },
  { label: "accent", swatch: "bg-accent" },
  { label: "success", swatch: "bg-success" },
  { label: "warning", swatch: "bg-warning" },
  { label: "info", swatch: "bg-info" },
  { label: "destructive", swatch: "bg-destructive" },
  { label: "border", swatch: "bg-border" },
  { label: "ring", swatch: "bg-ring" },
];

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="font-heading text-xl font-semibold tracking-tight">{title}</h2>
        <p className="text-muted-foreground text-sm">{description}</p>
      </div>
      <div className="bg-card flex flex-col gap-6 rounded-xl border p-6 shadow-sm">{children}</div>
    </section>
  );
}

function Row({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex flex-wrap items-center gap-3", className)}>{children}</div>;
}

function FoundationsSection() {
  return (
    <Section
      title="Foundations"
      description="Semantic color tokens, typography and status colors. Components consume tokens only — no raw values."
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {COLOR_TOKENS.map(({ label, swatch }) => (
          <div key={label} className="overflow-hidden rounded-lg border">
            <div className={cn("h-12 border-b", swatch)} />
            <div className="bg-card px-2 py-1.5 font-mono text-xs">{label}</div>
          </div>
        ))}
      </div>

      <Separator />

      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
          Typography · Lexend headings, Source Sans 3 body
        </p>
        <p className="font-heading text-4xl font-semibold tracking-tight">Join the meet</p>
        <p className="font-heading text-2xl font-medium">Meeting in progress</p>
        <p className="font-heading text-xl font-medium">Participant controls</p>
        <p className="text-base leading-relaxed">
          Body copy at 16px with a 1.5 line height. Procto keeps meetings legible: high-contrast
          text, calm rhythm, no gray-on-gray.
        </p>
        <p className="text-muted-foreground text-sm">
          Secondary text uses muted-foreground for supporting detail and timestamps.
        </p>
        <p className="font-mono text-sm">meet_9f3a-77c1 · 00:14:32</p>
      </div>
    </Section>
  );
}

function ButtonsSection() {
  return (
    <Section
      title="Buttons"
      description="Variants, sizes and states. Loading is composed with Spinner + disabled — never a separate loading component."
    >
      <Row>
        <Button>Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="destructive">Destructive</Button>
        <Button variant="success">Success</Button>
        <Button variant="link">Link</Button>
      </Row>

      <Row>
        <Button size="xs">Extra small</Button>
        <Button size="sm">Small</Button>
        <Button size="default">Default</Button>
        <Button size="lg">Large</Button>
      </Row>

      <Row>
        <Button size="icon-sm" aria-label="Settings">
          <SettingsIcon />
        </Button>
        <Button size="icon" aria-label="Profile">
          <UserIcon />
        </Button>
        <Button size="icon-lg" aria-label="Participants">
          <UsersIcon />
        </Button>
        <Button size="icon-xl" aria-label="Calendar">
          <CalendarIcon />
        </Button>
        <Button>
          <CircleCheckIcon data-icon="inline-start" />
          With leading icon
        </Button>
        <Button disabled>Disabled</Button>
        <Button disabled>
          <Spinner aria-hidden="true" data-icon="inline-start" />
          Joining
        </Button>
        <Button variant="outline" disabled>
          Disabled outline
        </Button>
      </Row>
    </Section>
  );
}

function FormsSection() {
  return (
    <Section
      title="Forms"
      description="FieldGroup + Field layout, validation via data-invalid on the Field and aria-invalid on the control."
    >
      <FieldGroup className="max-w-md">
        <Field>
          <FieldLabel htmlFor="meet-name">Meet name</FieldLabel>
          <Input id="meet-name" placeholder="Weekly sync" defaultValue="Weekly sync" />
          <FieldDescription>Shown to everyone you invite.</FieldDescription>
        </Field>

        <Field data-invalid>
          <FieldLabel htmlFor="meet-code">Invite code</FieldLabel>
          <Input id="meet-code" aria-invalid defaultValue="abc" />
          <FieldError>Codes are 8 characters, letters and numbers only.</FieldError>
        </Field>

        <Field>
          <FieldLabel htmlFor="meet-notes">Agenda</FieldLabel>
          <Textarea id="meet-notes" placeholder="What will you cover?" />
        </Field>

        <Field>
          <FieldLabel htmlFor="role">Default role</FieldLabel>
          <Select defaultValue="participant">
            <SelectTrigger id="role" className="w-full">
              <SelectValue placeholder="Select a role" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Meeting roles</SelectLabel>
                <SelectItem value="host">Host</SelectItem>
                <SelectItem value="moderator">Moderator</SelectItem>
                <SelectItem value="participant">Participant</SelectItem>
                <SelectItem value="observer">Observer</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          <FieldDescription>Applied when people join through your link.</FieldDescription>
        </Field>

        <Field>
          <Row className="gap-2">
            <Checkbox id="waiting-room" defaultChecked />
            <Label htmlFor="waiting-room">Enable waiting room</Label>
          </Row>
        </Field>

        <Field>
          <Row className="justify-between gap-2">
            <div className="flex flex-col gap-0.5">
              <Label htmlFor="mute-on-join">Mute on join</Label>
              <FieldDescription>Participants join muted by default.</FieldDescription>
            </div>
            <Switch id="mute-on-join" defaultChecked />
          </Row>
        </Field>
      </FieldGroup>
    </Section>
  );
}

function StatusSection() {
  const qualities = ["excellent", "good", "fair", "poor", "offline"] as const;

  return (
    <Section
      title="Status indicators"
      description="Meeting state always carries an icon or text alongside color — never color alone."
    >
      <Row>
        <StatusIndicator status="connecting" />
        <StatusIndicator status="connected" />
        <StatusIndicator status="reconnecting" />
        <StatusIndicator status="failed" />
        <LiveIndicator />
      </Row>

      <Row>
        {qualities.map((quality) => (
          <ConnectionQuality key={quality} quality={quality} />
        ))}
      </Row>

      <Row>
        <Badge>Primary</Badge>
        <Badge variant="secondary">Secondary</Badge>
        <Badge variant="outline">Outline</Badge>
        <Badge variant="destructive">Offline</Badge>
        <Badge variant="success">Ready</Badge>
        <Badge variant="warning">Unstable</Badge>
        <Badge variant="info">Sharing</Badge>
        <Badge variant="success">
          <CircleCheckIcon data-icon="inline-start" />
          Admitted
        </Badge>
      </Row>
    </Section>
  );
}

function DataSection() {
  return (
    <Section
      title="Cards, avatars & feedback primitives"
      description="Composition building blocks: full Card structure, avatars with fallbacks, skeletons, progress."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Design review</CardTitle>
            <CardDescription>Starts in 10 minutes · 4 invited</CardDescription>
            <CardAction>
              <Badge variant="success">Ready</Badge>
            </CardAction>
          </CardHeader>
          <CardContent className="flex items-center gap-3">
            <AvatarGroup>
              <Avatar>
                <AvatarFallback>AY</AvatarFallback>
              </Avatar>
              <Avatar>
                <AvatarFallback>CM</AvatarFallback>
              </Avatar>
              <Avatar>
                <AvatarFallback>PN</AvatarFallback>
              </Avatar>
            </AvatarGroup>
            <span className="text-muted-foreground text-sm">3 people confirmed</span>
          </CardContent>
          <CardFooter className="gap-2">
            <Button size="sm">Join early</Button>
            <Button size="sm" variant="outline">
              Details
            </Button>
          </CardFooter>
        </Card>

        <div className="flex flex-col gap-4">
          <Row>
            <Avatar className="size-8">
              <AvatarFallback>AY</AvatarFallback>
            </Avatar>
            <Avatar className="size-10">
              <AvatarFallback>CM</AvatarFallback>
              <AvatarBadge className="bg-success" aria-label="Connected" />
            </Avatar>
            <Avatar className="size-12">
              <AvatarFallback className="text-sm">PN</AvatarFallback>
            </Avatar>
            <span className="text-muted-foreground text-sm">Avatar always renders a fallback</span>
          </Row>

          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Shortcuts</span>
            <KbdGroup>
              <Kbd>Ctrl</Kbd>
              <Kbd>Shift</Kbd>
              <Kbd>M</Kbd>
            </KbdGroup>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Upload invite list</span>
              <Spinner aria-hidden="true" />
            </div>
            <Progress value={60}>
              <span className="text-muted-foreground text-sm">60%</span>
            </Progress>
          </div>

          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-20 w-full rounded-xl" />
          </div>
        </div>
      </div>
    </Section>
  );
}

function FeedbackSection() {
  return (
    <Section
      title="Feedback & async states"
      description="Alert for callouts, toasts for transient events, and dedicated loading / error / empty states for meeting surfaces."
    >
      <div className="grid gap-3">
        <Alert>
          <InfoIcon />
          <AlertTitle>Recording is on</AlertTitle>
          <AlertDescription>
            Everyone has been notified. You can pause or stop recording from the toolbar.
          </AlertDescription>
        </Alert>
        <Alert variant="success">
          <CircleCheckIcon />
          <AlertTitle>Admitted from waiting room</AlertTitle>
          <AlertDescription>Priya Nair joined the meet as a participant.</AlertDescription>
        </Alert>
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>Unstable connection</AlertTitle>
          <AlertDescription>Video quality was reduced to keep audio clear.</AlertDescription>
        </Alert>
        <Alert variant="info">
          <InfoIcon />
          <AlertTitle>Screen sharing paused</AlertTitle>
          <AlertDescription>Resume sharing when you are ready.</AlertDescription>
        </Alert>
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>Could not access the microphone</AlertTitle>
          <AlertDescription>Check your browser permissions, then try again.</AlertDescription>
        </Alert>
      </div>

      <Separator />

      <Row>
        <Button
          variant="outline"
          onClick={() =>
            toast.add({
              type: "success",
              title: "Invite link copied",
              description: "Share it with anyone you want in the meet.",
            })
          }
        >
          Success toast
        </Button>
        <Button
          variant="outline"
          onClick={() =>
            toast.add({
              type: "info",
              title: "Screen sharing started",
              description: "Participants can now see your screen.",
            })
          }
        >
          Info toast
        </Button>
        <Button
          variant="outline"
          onClick={() =>
            toast.add({
              type: "warning",
              title: "Connection is unstable",
              description: "Audio may cut out until the network recovers.",
            })
          }
        >
          Warning toast
        </Button>
        <Button
          variant="outline"
          onClick={() =>
            toast.add({
              type: "error",
              title: "Could not join the meet",
              description: "The meet may have ended or the link is invalid.",
            })
          }
        >
          Error toast
        </Button>
      </Row>

      <div className="grid gap-4">
        <MeetingLoadingState />
        <MeetingErrorState onRetry={() => toast.add({ type: "info", title: "Retrying…" })} />
        <MeetingEmptyState
          onAction={() => toast.add({ type: "success", title: "Invite link copied" })}
        />
      </div>
    </Section>
  );
}

function OverlaysSection() {
  return (
    <Section
      title="Overlays & navigation"
      description="Dialog for modals, AlertDialog for confirmations, Sheet for side panels, plus menus, popovers, tooltips and tabs."
    >
      <Row>
        <Dialog>
          <DialogTrigger render={<Button variant="outline">Open dialog</Button>} />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Leave the meet?</DialogTitle>
              <DialogDescription>
                You can rejoin with the same link while the meet is running.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter showCloseButton />
          </DialogContent>
        </Dialog>

        <AlertDialog>
          <AlertDialogTrigger render={<Button variant="outline">End for everyone</Button>} />
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>End the meet for everyone?</AlertDialogTitle>
              <AlertDialogDescription>
                All participants will be disconnected and the recording will stop.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                render={<Button variant="destructive" />}
                onClick={() => toast.add({ type: "error", title: "Meet ended" })}
              >
                End meet
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <Sheet>
          <SheetTrigger render={<Button variant="outline">Open side panel</Button>} />
          <SheetContent>
            <SheetHeader>
              <SheetTitle>Participants</SheetTitle>
              <SheetDescription>4 people in this meet right now.</SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-3 px-4 pb-4">
              {["Amina Yusuf", "Carlos Mendes", "Priya Nair", "Omar Haddad"].map((name) => (
                <div key={name} className="flex items-center gap-3">
                  <Avatar className="size-8">
                    <AvatarFallback>{name.slice(0, 2).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <span className="flex-1 truncate text-sm">{name}</span>
                </div>
              ))}
            </div>
          </SheetContent>
        </Sheet>

        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline">Open menu</Button>} />
          <DropdownMenuContent>
            <DropdownMenuLabel>Meeting</DropdownMenuLabel>
            <DropdownMenuItem onClick={() => toast.add({ type: "info", title: "Mute all" })}>
              Mute everyone
            </DropdownMenuItem>
            <DropdownMenuItem>Lock the meet</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive">Remove participant</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Popover>
          <PopoverTrigger render={<Button variant="outline">Open popover</Button>} />
          <PopoverContent>
            <p className="text-sm font-medium">Meeting ID</p>
            <p className="text-muted-foreground font-mono text-sm">meet_9f3a-77c1</p>
          </PopoverContent>
        </Popover>

        <Tooltip>
          <TooltipTrigger render={<Button variant="outline">Hover tooltip</Button>} />
          <TooltipContent>
            Tooltips explain controls
            <Kbd>M</Kbd>
          </TooltipContent>
        </Tooltip>
      </Row>

      <Tabs defaultValue="chat">
        <TabsList>
          <TabsTrigger value="chat">Chat</TabsTrigger>
          <TabsTrigger value="people">People</TabsTrigger>
          <TabsTrigger value="notes">Notes</TabsTrigger>
        </TabsList>
        <TabsContent value="chat" className="text-muted-foreground rounded-lg border p-4 text-sm">
          Message list would render here.
        </TabsContent>
        <TabsContent value="people" className="text-muted-foreground rounded-lg border p-4 text-sm">
          Participant list would render here.
        </TabsContent>
        <TabsContent value="notes" className="text-muted-foreground rounded-lg border p-4 text-sm">
          Shared meeting notes would render here.
        </TabsContent>
      </Tabs>
    </Section>
  );
}

function MeetingSection() {
  const [isPinned, setIsPinned] = React.useState(true);
  const [isReactionsOpen, setIsReactionsOpen] = React.useState(false);
  const [state, setState] = React.useState({
    isMicOn: true,
    isCameraOn: true,
    isScreenSharing: false,
    isHandRaised: false,
  });

  return (
    <Section
      title="Meeting UI"
      description="Domain primitives composed from the token and component layer: participant tiles, the Meet-style control dock, top bar, side panels and meeting states."
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <ParticipantTile name="Amina Yusuf" connection="excellent" />
        <ParticipantTile name="Carlos Mendes" isSpeaking connection="good" />
        <ParticipantTile
          name="Priya Nair"
          isMuted
          isCameraOff
          connection="poor"
          onPin={() => toast.add({ type: "info", title: "Pin controls are demo-only" })}
        />
        <ParticipantTile
          name="Omar Haddad"
          isHost
          isHandRaised
          isScreenSharing
          isPinned={isPinned}
          onPin={() => setIsPinned((pinned) => !pinned)}
          connection="excellent"
        />
        <div className="text-muted-foreground flex items-center justify-center rounded-xl border border-dashed p-4 text-sm sm:col-span-2 lg:col-span-2">
          Tiles show speaking rings, mute / camera state, host and hand badges, connection quality
          and pin affordances — all driven by props, no media pipeline yet.
        </div>
      </div>

      <Separator />

      <div className="flex flex-col items-start gap-3">
        <div className="flex flex-col items-start gap-3">
          {isReactionsOpen ? (
            <ReactionBar
              onReact={(label) => toast.add({ type: "success", title: `Reaction: ${label}` })}
              onCollapse={() => setIsReactionsOpen(false)}
            />
          ) : null}
          <MeetingControls
            state={state}
            isReactionsOpen={isReactionsOpen}
            onToggleMic={() => setState((s) => ({ ...s, isMicOn: !s.isMicOn }))}
            onToggleCamera={() => setState((s) => ({ ...s, isCameraOn: !s.isCameraOn }))}
            onToggleScreenShare={() =>
              setState((s) => ({ ...s, isScreenSharing: !s.isScreenSharing }))
            }
            onToggleHand={() => setState((s) => ({ ...s, isHandRaised: !s.isHandRaised }))}
            onOpenChat={() => toast.add({ type: "info", title: "Chat panel" })}
            onToggleReactions={() => setIsReactionsOpen((open) => !open)}
            onMoreAction={(action) => toast.add({ type: "info", title: `More: ${action}` })}
            onLeave={() => toast.add({ type: "warning", title: "You left the meet" })}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <UtilityCluster
            onOpenChat={() => toast.add({ type: "info", title: "Chat panel" })}
            onOpenPeople={() => toast.add({ type: "info", title: "People panel" })}
            onToggleHostControls={() => toast.add({ type: "info", title: "Host controls" })}
          />
          <MeetingTopBar
            code="ktq-vxm-pnz"
            time="10:24"
            participantCount={4}
            onShowDetails={() => toast.add({ type: "info", title: "Meeting details" })}
            onOpenPeople={() => toast.add({ type: "info", title: "People panel" })}
            className="flex-1 rounded-lg border px-3"
          />
        </div>
        <p className="text-muted-foreground text-sm">
          44×44px targets, aria-pressed on toggles, keyboard hints in tooltips, Meet-style pill dock
          with a separate utility cluster.
        </p>
      </div>

      <Separator />

      <div className="grid gap-3 lg:grid-cols-2">
        <PeoplePanel
          participants={[
            { id: "you", name: "Hasan", role: "Meeting host", isYou: true },
            { id: "amina", name: "Amina Yusuf", role: "Contributor" },
            { id: "carlos", name: "Carlos Mendes", role: "Contributor", isMuted: true },
          ]}
          onAddPeople={() => toast.add({ type: "info", title: "Invite people (demo)" })}
        />
        <ChatPanel
          messages={[
            { id: "1", author: "Amina Yusuf", text: "Agenda shared in the doc.", time: "10:12" },
            { id: "2", author: "Hasan", text: "Thanks — starting in two minutes.", time: "10:13" },
          ]}
          onSend={(text) => toast.add({ type: "success", title: `Sent: ${text}` })}
          className="min-h-96"
        />
      </div>
      <p className="text-muted-foreground text-sm">
        Side panels are presentational: search, collapsible groups, the messages switch and the
        composer are local UI state only.
      </p>
    </Section>
  );
}

function ShellSection() {
  const items = [
    { label: "Home", icon: HomeIcon },
    { label: "Meets", icon: VideoIcon },
    { label: "Participants", icon: UsersIcon },
    { label: "Chat", icon: MessageSquareIcon },
    { label: "Settings", icon: SettingsIcon },
  ];

  return (
    <Section
      title="App shell"
      description="Sidebar with grouped navigation, active state and a trigger — the shell meeting screens will mount into."
    >
      <div className="h-96 overflow-hidden rounded-lg border">
        <SidebarProvider>
          <Sidebar collapsible="icon">
            <SidebarHeader>
              <div className="flex items-center gap-2 px-2 py-1.5">
                <Avatar className="size-8">
                  <AvatarFallback>PR</AvatarFallback>
                </Avatar>
                <div className="flex min-w-0 flex-col group-data-[collapsible=icon]:hidden">
                  <span className="truncate text-sm font-semibold">Procto</span>
                  <span className="text-muted-foreground truncate text-xs">Workspace</span>
                </div>
              </div>
            </SidebarHeader>
            <SidebarContent>
              <SidebarGroup>
                <SidebarGroupLabel>Menu</SidebarGroupLabel>
                <SidebarMenu>
                  {items.map(({ label, icon: Icon }, index) => (
                    <SidebarMenuItem key={label}>
                      <SidebarMenuButton isActive={index === 1} tooltip={label} aria-label={label}>
                        <Icon />
                        <span>{label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroup>
            </SidebarContent>
            <SidebarFooter>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton tooltip="Account" aria-label="Account">
                    <UserIcon />
                    <span>Account</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarFooter>
          </Sidebar>
          <SidebarInset>
            <header className="flex h-12 items-center gap-2 border-b px-3">
              <SidebarTrigger />
              <span className="text-sm font-medium">Meets</span>
            </header>
            <div className="flex-1 p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>Weekly sync</CardTitle>
                    <CardDescription>Today · 14:00</CardDescription>
                  </CardHeader>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Design review</CardTitle>
                    <CardDescription>Tomorrow · 10:30</CardDescription>
                  </CardHeader>
                </Card>
              </div>
            </div>
          </SidebarInset>
        </SidebarProvider>
      </div>
    </Section>
  );
}

export default function DesignPage() {
  return (
    <div className="bg-background text-foreground min-h-svh">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-10 sm:px-6">
        <header className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="sm" render={<Link href="/" />}>
                <HomeIcon data-icon="inline-start" />
                Home
              </Button>
              <Badge variant="outline">Phase 1 · Design system</Badge>
            </div>
            <ThemeToggle />
          </div>
          <div className="flex flex-col gap-1">
            <h1 className="font-heading text-3xl font-semibold tracking-tight">
              Procto design system
            </h1>
            <p className="text-muted-foreground max-w-2xl text-sm">
              Every token, component and state that later phases compose from. Light and dark
              themes, keyboard-visible focus, and loading / error / empty states everywhere.
            </p>
          </div>
        </header>

        <FoundationsSection />
        <ButtonsSection />
        <FormsSection />
        <StatusSection />
        <DataSection />
        <FeedbackSection />
        <OverlaysSection />
        <MeetingSection />
        <ShellSection />
      </div>
    </div>
  );
}
