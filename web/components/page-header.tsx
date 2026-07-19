type Props = {
  title: string;
  description?: string;
};

export function PageHeader({ title, description }: Props) {
  return (
    <header className="mb-7">
      <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.035em]">{title}</h1>
      {description && (
        <p className="mt-2 max-w-2xl text-[15px] leading-6 text-muted-foreground">
          {description}
        </p>
      )}
    </header>
  );
}
