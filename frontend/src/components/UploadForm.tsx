import { useNavigate } from "react-router-dom"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useCreateDocument } from "@/hooks/useCreateDocument"
import { FILING_TYPES, FISCAL_PERIODS } from "@/lib/enums"
import { ApiError } from "@/api/client"

const currentYear = new Date().getFullYear()

const schema = z.object({
  file: z
    .instanceof(FileList)
    .refine((files) => files.length === 1, "A filing file is required."),
  ticker: z
    .string()
    .trim()
    .min(1, "Ticker is required.")
    .max(10, "That doesn't look like a ticker.")
    .regex(/^[A-Za-z.]+$/, "Tickers are letters only (e.g. AAPL)."),
  filing_type: z.enum(["10-K", "10-Q", "8-K", "DEF 14A", "other"], {
    message: "Filing type is required.",
  }),
  fiscal_year: z
    .number({ message: "Fiscal year is required." })
    .int()
    .min(1990, "Enter a realistic fiscal year.")
    .max(currentYear + 1, "Enter a realistic fiscal year."),
  fiscal_period: z.enum(["Q1", "Q2", "Q3", "Q4", "FY"], { message: "Fiscal period is required." }),
  period_end_date: z.string().optional(),
})

type FormValues = z.infer<typeof schema>

export function UploadForm() {
  const navigate = useNavigate()
  const { mutate, isPending } = useCreateDocument()
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { fiscal_year: currentYear },
  })

  function onSubmit(values: FormValues) {
    mutate(
      {
        file: values.file[0],
        ticker: values.ticker.toUpperCase(),
        filing_type: values.filing_type,
        fiscal_year: values.fiscal_year,
        fiscal_period: values.fiscal_period,
        period_end_date: values.period_end_date || null,
      },
      {
        onSuccess: (document) => {
          toast.success("Filing submitted — review is running.")
          navigate(`/documents/${document.id}`)
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 422) {
            toast.error("The backend rejected one of the fields — check your inputs.")
          } else {
            toast.error("Couldn't submit the filing. Please try again.")
          }
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 max-w-xl">
      <div>
        <Label htmlFor="file" className="mb-1.5">
          Filing (.txt)
        </Label>
        <Input id="file" type="file" accept=".txt,text/plain" {...register("file")} />
        {errors.file && <p className="text-xs text-destructive mt-1">{errors.file.message}</p>}
      </div>

      <div>
        <Label htmlFor="ticker" className="mb-1.5">
          Ticker
        </Label>
        <Input id="ticker" placeholder="AAPL" {...register("ticker")} />
        {errors.ticker && <p className="text-xs text-destructive mt-1">{errors.ticker.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label className="mb-1.5">Filing type</Label>
          <Controller
            name="filing_type"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {FILING_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          {errors.filing_type && <p className="text-xs text-destructive mt-1">{errors.filing_type.message}</p>}
        </div>

        <div>
          <Label className="mb-1.5">Fiscal period</Label>
          <Controller
            name="fiscal_period"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select period" />
                </SelectTrigger>
                <SelectContent>
                  {FISCAL_PERIODS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          {errors.fiscal_period && <p className="text-xs text-destructive mt-1">{errors.fiscal_period.message}</p>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="fiscal_year" className="mb-1.5">
            Fiscal year
          </Label>
          <Input
            id="fiscal_year"
            type="number"
            {...register("fiscal_year", { valueAsNumber: true })}
          />
          {errors.fiscal_year && <p className="text-xs text-destructive mt-1">{errors.fiscal_year.message}</p>}
        </div>
        <div>
          <Label htmlFor="period_end_date" className="mb-1.5">
            Period end date (optional)
          </Label>
          <Input id="period_end_date" type="date" {...register("period_end_date")} />
        </div>
      </div>

      <Button type="submit" disabled={isPending} className="mt-2">
        {isPending ? "Submitting..." : "Submit for review"}
      </Button>
    </form>
  )
}
