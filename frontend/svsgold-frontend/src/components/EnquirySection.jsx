import React, { useEffect, useRef, useState } from 'react'
import {
  Save,
  Loader2,
  CheckCircle2,
  User,
  Phone,
  Wallet,
  CalendarDays,
  FileText,
  Pencil,
  X
} from 'lucide-react'
import { enquiriesAPI, applicationsAPI } from '../api/api'
import * as XLSX from 'xlsx'

const enquiryTypes = [
  'Sell Gold',
  'Pledge Gold'
]

const salutations = [
  'Mr',
  'Mrs',
  'Ms',
  'Dr',
  'Prof',
  'Other'
]

const sourceOptions = [
  'Facebook',
  'Direct Inbound',
  '3DM Inbound',
  'Instagram',
  'Youtube',
  'Google Ads',
  'Google Search',
  'Chatbot'
]

const defaultOrnamentTypes = [
  'Ring',
  'Chain',
  'Bangle',
  'Bracelet',
  'Earrings',
  'Pendant',
  'Other'
]

const priorityOptions = ['Low', 'Medium', 'High']
const leadStateOptions = ['New', 'Qualified', 'Disqualified']
const leadStatusOptions = ['Open', 'Answered', 'Not Answered']
const leadStageOptions = ['Enquiry', 'Gold Loan', 'Already sold', 'Processing fee','Non local','Not interested','Follow-up later','Junk','Converted','Others']

const initialForm = {
  salutation: 'Mr',
  name: '',
  mobile: '',
  email: '',
  branch: '',
  enquiry_type: 'Sell Gold',
  product_interest: '',
  source: 'Walk-in',
  ornament_type: 'Ring',
  processing_fee: '',
  gross_weight_gms: '',
  net_weight_gms: '',
  purity_percentage: '',
  rate: '',
  pledge_amount: '',
  financier_name: '',
  financier_branch: '',
  lead_state: 'New',
  lead_status: 'Open',
  lead_stage: 'Enquiry',
  follow_up_date: '',
  priority: 'Medium',
  remarks: ''
}

export default function Enquiry() {
  const [formOpen, setFormOpen] = useState(false)
  const [editingEnquiry, setEditingEnquiry] = useState(null)
  const [form, setForm] = useState(initialForm)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')
  const [recentEnquiries, setRecentEnquiries] = useState([])
  const [loadingRecent, setLoadingRecent] = useState(false)
  const [branches, setBranches] = useState([])
  const [ornamentTypes, setOrnamentTypes] = useState(defaultOrnamentTypes)
  const [pastFilter, setPastFilter] = useState({
    date_from: '',
    date_to: '',
    enquiry_type: '',
    branch: '',
    mobile: '',
    follow_up_date: '',
    lead_state: '',
    lead_status: '',
    lead_stage: '',
    sort_order: 'desc'
  })
  const [pastEnquiries, setPastEnquiries] = useState([])
  const [loadingPast, setLoadingPast] = useState(false)
  const [pastError, setPastError] = useState('')

const grossAmount = (() => {
  const netWeight =
    parseFloat(
      form.net_weight_gms
    ) || 0

  const purity =
    parseFloat(
      form.purity_percentage
    ) || 0

  const dayRate =
    parseFloat(form.rate) || 0

  if (
    !netWeight ||
    !purity ||
    !dayRate
  ) {
    return 0
  }

  return (
    netWeight *
    dayRate *
    (purity / 100)
  )
})()

const netAmount = (() => {
  const gross =
    Number(grossAmount) || 0

  if (!gross) return 0

  const processingFee =
    parseFloat(
      form.processing_fee
    ) || 0

  // PF deduction
  const pfDeduction =
    gross *
    (processingFee / 100)

  // After PF
  const afterPF =
    gross - pfDeduction

  // Pledge Gold
  if (
    form.enquiry_type ===
    'Pledge Gold'
  ) {
    const pledgeAmount =
      parseFloat(
        form.pledge_amount
      ) || 0

    return (
      afterPF -
      pledgeAmount
    )
  }

  // Sell Gold
  return afterPF
})()


  useEffect(() => {
    const loadBranches = async () => {
      try {
        const response = await applicationsAPI.getBranches()
        setBranches(response?.data?.branches || [])
      } catch (err) {
        setBranches([])
      }
    }

    const loadGoldItems = async () => {
      try {
        const response = await applicationsAPI.getGoldItems()
        const items = response?.data?.gold_items || []
        if (items.length > 0) {
          const names = items.map((item) => item.name)
          setOrnamentTypes(names)
          setForm((prev) => ({
            ...prev,
            ornament_type: names.includes(prev.ornament_type)
              ? prev.ornament_type
              : names[0]
          }))
        }
      } catch (err) {
        setOrnamentTypes(defaultOrnamentTypes)
      }
    }

    loadBranches()
    loadGoldItems()
  }, [])

  const handleChange = (key, value) => {
    setForm(prev => ({
      ...prev,
      [key]: value
    }))

    if (key === 'mobile' && value.length >= 10) {
      loadRecentEnquiries(value)
    }
  }

  const loadRecentEnquiries = async (mobile) => {
    try {
      setLoadingRecent(true)

      const response =
        await enquiriesAPI.getByMobile(mobile)

      setRecentEnquiries(
        response?.data?.enquiries || []
      )
    } catch (err) {
      setRecentEnquiries([])
    } finally {
      setLoadingRecent(false)
    }
  }

  const handlePastFilterChange = (key, value) => {
    setPastFilter((prev) => ({
      ...prev,
      [key]: value
    }))
  }

  const loadPastEnquiries = async () => {
    try {
      setLoadingPast(true)
      setPastError('')

      const response = await enquiriesAPI.getByDate({
        dateFrom: pastFilter.date_from,
        dateTo: pastFilter.date_to,
        enquiryType: pastFilter.enquiry_type,
        branch: pastFilter.branch,
        mobile: pastFilter.mobile,
        followUpDate: pastFilter.follow_up_date,
        leadState: pastFilter.lead_state,
        leadStatus: pastFilter.lead_status,
        leadStage: pastFilter.lead_stage,
        sortOrder: pastFilter.sort_order
      })

      setPastEnquiries(response?.data?.enquiries || [])
    } catch (err) {
      setPastEnquiries([])
      setPastError(
        err.response?.data?.detail ||
          'Unable to fetch past enquiries'
      )
    } finally {
      setLoadingPast(false)
    }
  }

  const formatDateForInput = (value) => {
    if (!value) return ''
    return value.toString().slice(0, 10)
  }

  const openNewEnquiry = () => {
    setEditingEnquiry(null)
    setForm(initialForm)
    setError('')
    setSuccess('')
    setFormOpen(true)
  }

  const openEditEnquiry = (item) => {
    setEditingEnquiry(item)
    setForm({
      ...initialForm,
      salutation: item.salutation || initialForm.salutation,
      name: item.name || '',
      mobile: item.mobile || '',
      email: item.email || '',
      branch: item.branch || '',
      enquiry_type: item.enquiry_type || initialForm.enquiry_type,
      product_interest: item.product_interest || '',
      source: item.source || initialForm.source,
      ornament_type: item.ornament_type || initialForm.ornament_type,
      processing_fee: item.processing_fee ?? '',
      gross_weight_gms: item.gross_weight_gms ?? '',
      net_weight_gms: item.gold_weight_gms ?? '',
      purity_percentage: item.purity_percentage ?? '',
      rate: item.rate ?? '',
      pledge_amount: item.pledge_amount ?? '',
      financier_name: item.financier_name || '',
      financier_branch: item.financier_branch || '',
      lead_state: item.lead_state || initialForm.lead_state,
      lead_status: item.lead_status || initialForm.lead_status,
      lead_stage: item.lead_stage || initialForm.lead_stage,
      follow_up_date: formatDateForInput(item.follow_up_date),
      priority: item.priority || initialForm.priority,
      remarks: item.remarks || ''
    })
    setError('')
    setSuccess('')
    setFormOpen(true)
  }

  const closeForm = () => {
    setFormOpen(false)
    setEditingEnquiry(null)
    setError('')
    setSuccess('')
  }

  const exportPastEnquiries = () => {
    if (pastEnquiries.length === 0) {
      setPastError('No results available to export')
      return
    }

    const rows = pastEnquiries.map((item) => ({
      Enquiry_ID: item.enquiry_id || '',
      Date: formatDateTime(item.created_at),
      Salutation: item.salutation || '',
      Customer: item.name || '',
      Mobile: item.mobile || '',
      Email: item.email || '',
      Branch: item.branch || '',
      Category: item.enquiry_type || '',
      Product_Interest: item.product_interest || '',
      Source: item.source || '',
      Ornament_Type: item.ornament_type || '',
      Processing_Fee_Percentage: item.processing_fee || '',
      Gross_Amount: item.expected_amount || '',
      Gross_Weight_Gms: item.gross_weight_gms || '',
      Net_Weight_Gms: item.gold_weight_gms || '',
      Purity_Percentage: item.purity_percentage || '',
      Day_Rate: item.rate || '',
      Net_Amount: item.net_amount || '',
      Pledge_Amount: item.pledge_amount || '',
      Financier_Name: item.financier_name || '',
      Financier_Branch: item.financier_branch || '',
      Lead_State: item.lead_state || '',
      Lead_Status: item.lead_status || '',
      Lead_Stage: item.lead_stage || '',
      Follow_Up_Date: item.follow_up_date || '',
      Priority: item.priority || '',
      Remarks: item.remarks || ''
    }))

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Past Enquiries')
    const dateSuffix = new Date().toISOString().slice(0, 10)
    XLSX.writeFile(wb, `past-enquiries-${dateSuffix}.xlsx`)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    setError('')
    setSuccess('')

  // Customer Information
  if (!form.salutation?.trim()) {
    setError('Salutation is required')
    return
  }

  if (!form.name?.trim()) {
    setError('Customer name is required')
    return
  }

  if (!form.mobile?.trim()) {
    setError('Mobile number is required')
    return
  }

  // Mobile validation
  if (!/^\d{10}$/.test(form.mobile.trim())) {
    setError(
      'Mobile number must be exactly 10 digits'
    )
    return
  }

  if (!form.branch?.trim()) {
    setError('Branch is required')
    return
  }

  // Enquiry Details
  if (!form.enquiry_type?.trim()) {
    setError('Enquiry type is required')
    return
  }

  if (!form.source?.trim()) {
    setError('Source is required')
    return
  }

  // Gold Details
  if (!form.ornament_type?.trim()) {
    setError('Ornament type is required')
    return
  }

  if (
    !form.processing_fee &&
    form.processing_fee !== 0
  ) {
    setError(
      'Processing fee is required'
    )
    return
  }

  if (!form.gross_weight_gms) {
    setError(
      'Gross weight is required'
    )
    return
  }

  if (!form.net_weight_gms) {
    setError(
      'Net weight is required'
    )
    return
  }

  if (!form.purity_percentage) {
    setError('Purity is required')
    return
  }

  if (!form.rate) {
    setError('Day rate is required')
    return
  }

  // Pledge Gold validations
  if (
    form.enquiry_type ===
    'Pledge Gold'
  ) {
    if (!form.pledge_amount) {
      setError(
        'Pledge amount is required'
      )
      return
    }

    if (
      !form.financier_name?.trim()
    ) {
      setError(
        'Financier name is required'
      )
      return
    }

    if (
      !form.financier_branch?.trim()
    ) {
      setError(
        'Financier branch is required'
      )
      return
    }
  }

  // Leads
  if (!form.lead_state?.trim()) {
    setError(
      'Lead state is required'
    )
    return
  }

  if (!form.lead_status?.trim()) {
    setError(
      'Lead status is required'
    )
    return
  }

  if (!form.lead_stage?.trim()) {
    setError(
      'Lead stage is required'
    )
    return
  }

  // Follow-up
  if (!form.follow_up_date) {
    setError(
      'Follow-up date is required'
    )
    return
  }

  // Remarks
  if (!form.remarks?.trim()) {
    setError('Remarks are required')
    return
  }

// Only 10 digit mobile validation
if (!/^\d{10}$/.test(form.mobile.trim())) {
  setError(
    'Mobile number must be exactly 10 digits'
  )
  return
}
const numericFields = [
  {
    key: 'processing_fee',
    label: 'Processing fee'
  },
  {
    key: 'gross_weight_gms',
    label: 'Gross weight'
  },
  {
    key: 'net_weight_gms',
    label: 'Net weight'
  },
  {
    key: 'purity_percentage',
    label: 'Purity'
  },
  {
    key: 'rate',
    label: 'Day rate'
  },
  {
    key: 'pledge_amount',
    label: 'Pledge amount'
  }
]

for (const field of numericFields) {
  const value = Number(
    form[field.key]
  )

  if (
    form[field.key] !== '' &&
    value < 0
  ) {
    setError(
      `${field.label} cannot be negative`
    )
    return
  }
}
  // Ensure processing fee is greater than 0.5% when provided
  if (form.processing_fee !== '' && Number(form.processing_fee) <= 0.5) {
    setError('Processing fee must be greater than 0.5%')
    return
  }
    setSaving(true)

    try {
      const payload = {
        name: form.name.trim(),
        salutation: form.salutation,
        mobile: form.mobile.trim(),
        email: form.email.trim() || null,
        branch: form.branch,
        enquiry_type: form.enquiry_type,
        product_interest: form.product_interest,
        source: form.source,
        ornament_type: form.ornament_type,
        processing_fee: form.processing_fee
          ? parseFloat(
              form.processing_fee
            )
          : null,
        expected_amount: grossAmount
          ? parseFloat(
              grossAmount
            )
          : null,
        gross_weight_gms: form.gross_weight_gms
          ? parseFloat(form.gross_weight_gms)
          : null,
        gold_weight_gms: form.net_weight_gms
          ? parseFloat(form.net_weight_gms)
          : null,
        purity_percentage:
          form.purity_percentage
            ? parseFloat(
                form.purity_percentage
              )
            : null,
        pledge_amount: form.pledge_amount
          ? parseFloat(form.pledge_amount)
          : null,
        rate: form.rate
          ? parseFloat(form.rate)
          : null,
        net_amount: netAmount
          ? parseFloat(netAmount)
          : null,
        financier_name: form.financier_name,
        financier_branch: form.financier_branch,
        lead_state: form.lead_state,
        lead_status: form.lead_status,
        lead_stage: form.lead_stage,
        follow_up_date: form.follow_up_date || null,
        priority: form.priority,
        remarks: form.remarks
      }

      const response = editingEnquiry
        ? await enquiriesAPI.updateEnquiry({
            enquiry_id: editingEnquiry.enquiry_id,
            ...payload
          })
        : await enquiriesAPI.createEnquiry(
            payload
          )

      setSuccess(
        editingEnquiry
          ? `Enquiry updated successfully (ID: ${response.data.enquiry_id})`
          : `Enquiry saved successfully (ID: ${response.data.enquiry_id})`
      )

      if (!editingEnquiry) {
        setForm({
          ...initialForm,
          mobile: form.mobile
        })
      }

      loadRecentEnquiries(form.mobile)
      if (pastEnquiries.length > 0) {
        loadPastEnquiries()
      }

      // Close the form after 2 seconds
      setTimeout(() => {
        closeForm()
      }, 2000)
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Unable to save enquiry'
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4 lg:p-6 bg-[#F8F6F1] min-h-screen">
      <div className="bg-white rounded-3xl shadow-xl border border-[#E5D2A0] overflow-hidden">

        {/* HEADER */}
        <div className="bg-gradient-to-r from-[#7A4E0B] via-[#A9741F] to-[#D4A437] px-6 py-5 border-b border-[#D6B36A]">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white tracking-wide">
                Enquiry Form
              </h2>

              <p className="text-amber-100 text-sm mt-1">
                Customer enquiry & lead management
              </p>
            </div>

            <div className="hidden md:flex items-center gap-2 bg-white/10 px-4 py-2 rounded-xl border border-white/20">
              <FileText
                size={18}
                className="text-amber-200"
              />

              <span className="text-white text-sm font-medium">
                CRM Enquiry
              </span>
            </div>
          </div>
        </div>

        <div className="p-5 space-y-6">
          <div className="bg-white border border-[#E5D2A0] rounded-2xl p-5 shadow-sm">
            <h3 className="font-bold text-gray-800 mb-4">
              Past Enquiries
            </h3>

            <div className="grid md:grid-cols-2 xl:grid-cols-5 gap-4">
              <InputField
                label="Phone Number"
                value={pastFilter.mobile}
                onChange={(v) =>
                  handlePastFilterChange('mobile', v)
                }
              />

              <InputField
                type="date"
                label="From Date"
                value={pastFilter.date_from}
                onChange={(v) =>
                  handlePastFilterChange('date_from', v)
                }
              />

              <InputField
                type="date"
                label="To Date"
                value={pastFilter.date_to}
                onChange={(v) =>
                  handlePastFilterChange('date_to', v)
                }
              />

              <SelectField
                label="Category"
                value={pastFilter.enquiry_type}
                options={enquiryTypes}
                placeholder="All categories"
                onChange={(v) =>
                  handlePastFilterChange('enquiry_type', v)
                }
              />

              <SelectField
                label="Branch"
                value={pastFilter.branch}
                options={branches.map((branch) => branch.branch_name)}
                placeholder="All branches"
                onChange={(v) =>
                  handlePastFilterChange('branch', v)
                }
              />

              <InputField
                type="date"
                label="Follow-up Date"
                value={pastFilter.follow_up_date}
                onChange={(v) =>
                  handlePastFilterChange('follow_up_date', v)
                }
              />

              <SelectField
                label="Lead State"
                value={pastFilter.lead_state}
                options={leadStateOptions}
                placeholder="All lead states"
                onChange={(v) =>
                  handlePastFilterChange('lead_state', v)
                }
              />

              <SelectField
                label="Lead Status"
                value={pastFilter.lead_status}
                options={leadStatusOptions}
                placeholder="All lead statuses"
                onChange={(v) =>
                  handlePastFilterChange('lead_status', v)
                }
              />

              <SelectField
                label="Lead Stage"
                value={pastFilter.lead_stage}
                options={leadStageOptions}
                placeholder="All lead stages"
                onChange={(v) =>
                  handlePastFilterChange('lead_stage', v)
                }
              />

              <SelectField
                label="Sort Order"
                value={pastFilter.sort_order}
                options={['desc', 'asc']}
                onChange={(v) =>
                  handlePastFilterChange('sort_order', v)
                }
              />
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={loadPastEnquiries}
                disabled={loadingPast}
                className="bg-gradient-to-r from-[#8B5E12] via-[#B67D22] to-[#D4A437] hover:opacity-95 transition-all text-white font-semibold rounded-2xl px-5 py-3 flex items-center gap-2 shadow-lg"
              >
                {loadingPast && (
                  <Loader2
                    size={16}
                    className="animate-spin"
                  />
                )}
                {loadingPast
                  ? 'Fetching...'
                  : 'Fetch Past Enquiries'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setPastFilter({
                    date_from: '',
                    date_to: '',
                    enquiry_type: '',
                    branch: '',
                    mobile: '',
                    follow_up_date: '',
                    lead_state: '',
                    lead_status: '',
                    lead_stage: '',
                    sort_order: 'desc'
                  })
                  setPastEnquiries([])
                  setPastError('')
                }}
                className="rounded-2xl border border-[#D8C08A] px-5 py-3 font-semibold text-gray-700 hover:bg-[#FFF8E8] transition-all"
              >
                Clear
              </button>

              <button
                type="button"
                onClick={exportPastEnquiries}
                className="rounded-2xl border border-[#D8C08A] px-5 py-3 font-semibold text-gray-700 hover:bg-[#FFF8E8] transition-all"
              >
                Export Results
              </button>
            </div>

            {pastError && (
              <div className="mt-4 bg-red-50 border border-red-200 text-red-600 rounded-xl px-4 py-3 text-sm">
                {pastError}
              </div>
            )}

            <div className="mt-5 max-h-[360px] overflow-auto rounded-xl border border-[#E8D5A8]">
              <table className="w-full min-w-[960px] text-sm">
                <thead className="sticky top-0 z-10 bg-[#FFF4D6]">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Date</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Customer</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Mobile</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Category</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Source</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Net Weight</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Pledge Amount</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Follow-up Date</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Lead State</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Lead Status</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Lead Stage</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Remarks</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Branch</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Action</th>
                  </tr>
                </thead>

                <tbody>
                  {pastEnquiries.length > 0 ? (
                    pastEnquiries.map((item) => (
                      <tr
                        key={item.enquiry_id}
                        className="border-t border-[#E8D5A8] bg-[#FFFDF8]"
                      >
                        <td className="px-4 py-3 text-gray-700">
                          {formatDateTime(item.created_at)}
                        </td>
                        <td className="px-4 py-3 text-gray-800">
                          {item.name || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.mobile || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.enquiry_type || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
  {item.source || '—'}
</td>
                      <td className="px-4 py-3 text-gray-700 font-medium">
  {item.gold_weight_gms
    ? Number(
        item.gold_weight_gms
      ).toLocaleString(
        'en-IN',
        {
          minimumFractionDigits: 0,
          maximumFractionDigits: 2,
        }
      )
    : '—'}
</td>

<td className="px-4 py-3 text-gray-700 font-medium">
  {item.pledge_amount
    ? `₹${Number(
        item.pledge_amount
      ).toLocaleString(
        'en-IN'
      )}`
    : '—'}
</td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.follow_up_date || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.lead_state || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.lead_status || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.lead_stage || '—'}
                        </td>
                        <td
  className="px-4 py-3 text-gray-700 max-w-[220px] truncate"
  title={item.remarks}
>
  {item.remarks || '—'}
</td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.branch || '—'}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={() => openEditEnquiry(item)}
                            className="inline-flex items-center gap-2 rounded-xl border border-[#D8C08A] px-3 py-2 text-sm font-semibold text-[#8B5E12] hover:bg-[#FFF8E8] transition-all"
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                          colSpan="10"
                          className="px-4 py-6 text-center text-gray-500 bg-[#FFFDF8]"
                        >
                        {loadingPast
                          ? 'Loading past enquiries...'
                          : 'No past enquiries found'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {!formOpen && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={openNewEnquiry}
                className="bg-gradient-to-r from-[#8B5E12] via-[#B67D22] to-[#D4A437] hover:opacity-95 transition-all text-white font-semibold rounded-2xl px-8 py-3 shadow-lg"
              >
                + New Enquiry
              </button>
            </div>
          )}

          {/* MODAL OVERLAY */}
          {formOpen && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
              <div className="bg-white rounded-3xl shadow-2xl border border-[#E5D2A0] overflow-hidden max-w-6xl w-full max-h-[90vh] flex flex-col">
                
                {/* MODAL HEADER */}
                <div className="bg-gradient-to-r from-[#7A4E0B] via-[#A9741F] to-[#D4A437] px-6 py-5 border-b border-[#D6B36A] flex items-center justify-between flex-shrink-0">
                  <div>
                    <h2 className="text-2xl font-bold text-white tracking-wide">
                      {editingEnquiry ? 'Edit Enquiry' : 'New Enquiry'}
                    </h2>
                    <p className="text-amber-100 text-sm mt-1">
                      Customer enquiry & lead management
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={closeForm}
                    className="bg-white/20 hover:bg-white/30 transition-all rounded-full p-2 flex items-center justify-center"
                  >
                    <X size={24} className="text-white" />
                  </button>
                </div>

                {/* MODAL CONTENT */}
                <form
                  onSubmit={handleSubmit}
                  className="p-5 overflow-y-auto flex-1"
                >

                  <div className="grid xl:grid-cols-[minmax(0,1.8fr)_340px] gap-6 h-fit">

                  {/* LEFT SECTION */}
                  <div className="space-y-5">

            {/* CUSTOMER INFO */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <User
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Customer Information
                </h3>
              </div>

              <div className="grid md:grid-cols-2 gap-4">

                <SelectField
                  label="Salutation"
                  value={form.salutation}
                  options={salutations}
                  onChange={(v) =>
                    handleChange('salutation', v)
                  }
                />

                <InputField
                  label="Customer Name *"
                  value={form.name}
                  onChange={(v) =>
                    handleChange('name', v)
                  }
                />

<InputField
  label="Mobile Number *"
  type="tel"
  value={form.mobile}
  maxLength={10}
  onChange={(v) =>
    handleChange(
      'mobile',
      v
        .replace(/\D/g, '') // only digits
        .slice(0, 10) // max 10 digits
    )
  }
/>

                <InputField
                  label="Email"
                  value={form.email}
                  onChange={(v) =>
                    handleChange('email', v)
                  }
                />

                <SelectField
                  label="Branch"
                  value={form.branch}
                  options={branches.map((branch) => branch.branch_name)}
                  placeholder="Select branch"
                  onChange={(v) =>
                    handleChange('branch', v)
                  }
                />
              </div>
            </div>

            {/* ENQUIRY DETAILS */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <Phone
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Enquiry Details
                </h3>
              </div>

              <div className="grid md:grid-cols-2 gap-4">

                <SelectField
                  label="Enquiry Type"
                  value={form.enquiry_type}
                  options={enquiryTypes}
                  onChange={(v) =>
                    handleChange(
                      'enquiry_type',
                      v
                    )
                  }
                />

                {/* <InputField
                  label="Product / Service"
                  value={form.product_interest}
                  onChange={(v) =>
                    handleChange(
                      'product_interest',
                      v
                    )
                  }
                /> */}

                <SelectField
                  label="Source"
                  value={form.source}
                  options={sourceOptions}
                  onChange={(v) =>
                    handleChange('source', v)
                  }
                />

                <SelectField
                  label="Priority"
                  value={form.priority}
                  options={priorityOptions}
                  onChange={(v) =>
                    handleChange('priority', v)
                  }
                />
              </div>
            </div>

            {/* GOLD DETAILS */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <Wallet
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Gold Details
                </h3>
              </div>

              <div className="grid md:grid-cols-3 gap-4">
                <SelectField
                  label="Ornament Type"
                  value={form.ornament_type}
                  options={ornamentTypes}
                  onChange={(v) =>
                    handleChange('ornament_type', v)
                  }
                />

                  <InputField
                    type="number"
                    label="Processing Fee (%)"
                    value={form.processing_fee}
                    onChange={(v) =>
                      handleChange(
                        'processing_fee',
                        Math.max(
                          0,
                          Number(v)
                        ) || ''
                      )
                    }
                  />

                <InputField
                  type="number"
                  label="Gross Weight (g)"
                  value={form.gross_weight_gms}
                  onChange={(v) =>
                    handleChange(
                      'gross_weight_gms',
                      Math.max(
                        0,
                        Number(v)
                      ) || ''
                    )
                  }
                />

                <InputField
                  type="number"
                  label="Net Weight (g)"
                  value={form.net_weight_gms}
                  onChange={(v) =>
                    handleChange(
                      'net_weight_gms',
                      Math.max(
                        0,
                        Number(v)
                      ) || ''
                    )
                  }
                />

                <InputField
                  type="number"
                  label="Purity (%)"
                  value={form.purity_percentage}
                  onChange={(v) =>
                    handleChange(
                      'purity_percentage',
                      Math.max(
                        0,
                        Number(v)
                      ) || ''
                    )
                  }
                />

                <InputField
                  type="number"
                  label="Day Rate"
                  value={form.rate}
                  onChange={(v) =>
                    handleChange(
                      'rate',
                      Math.max(
                        0,
                        Number(v)
                      ) || ''
                    )
                  }
                />
              </div>

<div
  className={`mt-4 grid gap-4 ${
    form.enquiry_type ===
    'Pledge Gold'
      ? 'md:grid-cols-3'
      : 'md:grid-cols-2'
  }`}
>

  {/* Gross Amount */}
  <InputField
    type="text"
    label="Gross Amount"
    value={
      grossAmount
        ? grossAmount.toFixed(
            2
          )
        : ''
    }
    readOnly
  />

  {/* Net Amount (after PF deduction) */}
  <InputField
    type="text"
    label="Net Amount"
    value={
      (() => {
        const gross =
          Number(
            grossAmount
          ) || 0

        const pf =
          parseFloat(
            form.processing_fee
          ) || 0

        const deduction =
          gross *
          (pf / 100)

        return gross
          ? (
              gross -
              deduction
            ).toFixed(2)
          : ''
      })()
    }
    readOnly
  />

  {/* Balance Amount - Pledge Gold only */}
  {form.enquiry_type ===
    'Pledge Gold' && (
    <InputField
      type="text"
      label="Balance Amount"
      value={
        netAmount
          ? netAmount.toFixed(
              2
            )
          : ''
      }
      readOnly
    />
  )}
</div>

              {form.enquiry_type === 'Pledge Gold' && (
                <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5 mt-5">
                  <div className="flex items-center gap-2 mb-4">
                    <Wallet
                      size={18}
                      className="text-[#A9741F]"
                    />

                    <h3 className="font-semibold text-gray-800">
                      Pledge Details
                    </h3>
                  </div>

                  <div className="grid md:grid-cols-3 gap-4">
                    <InputField
                      type="number"
                      label="Pledge Amount"
                      value={form.pledge_amount}
                      onChange={(v) =>
                        handleChange(
                          'pledge_amount',
                          Math.max(
                            0,
                            Number(v)
                          ) || ''
                        )
                      }
                    />

                    <InputField
                      label="Financier Name"
                      value={form.financier_name}
                      onChange={(v) =>
                        handleChange('financier_name', v)
                      }
                    />

                    <InputField
                      label="Financier Branch"
                      value={form.financier_branch}
                      onChange={(v) =>
                        handleChange('financier_branch', v)
                      }
                    />
                  </div>
                </div>
              )}

              <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5 mt-5">
                <div className="flex items-center gap-2 mb-4">
                  <FileText
                    size={18}
                    className="text-[#A9741F]"
                  />

                  <h3 className="font-semibold text-gray-800">
                    Leads
                  </h3>
                </div>

                <div className="grid md:grid-cols-3 gap-4">
                  <SelectField
                    label="Lead State"
                    value={form.lead_state}
                    options={leadStateOptions}
                    onChange={(v) =>
                      handleChange('lead_state', v)
                    }
                  />

                  <SelectField
                    label="Lead Status"
                    value={form.lead_status}
                    options={leadStatusOptions}
                    onChange={(v) =>
                      handleChange('lead_status', v)
                    }
                  />

                  <SelectField
                    label="Lead Stage"
                    value={form.lead_stage}
                    options={leadStageOptions}
                    onChange={(v) =>
                      handleChange('lead_stage', v)
                    }
                  />
                </div>
              </div>
            </div>

            {/* FOLLOWUP */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <CalendarDays
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Follow-up Details
                </h3>
              </div>

                <div className="grid md:grid-cols-2 gap-4">

                <InputField
                  type="date"
                  label="Follow-up Date"
                  value={form.follow_up_date}
                  onChange={(v) =>
                    handleChange(
                      'follow_up_date',
                      v
                    )
                  }
                />

                <div />
              </div>

              <div className="mt-4">
                <label className="text-sm font-medium text-gray-700">
                  Remarks
                </label>

                <textarea
                  rows={4}
                  value={form.remarks}
                  onChange={(e) =>
                    handleChange(
                      'remarks',
                      e.target.value
                    )
                  }
                  className="mt-1 w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 outline-none focus:border-[#B67D22]"
                  placeholder="Enter customer remarks..."
                />
              </div>
            </div>

            {/* ALERTS */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-600 rounded-xl px-4 py-3 text-sm">
                {error}
              </div>
            )}

            {success && (
              <div className="bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm flex items-center gap-2">
                <CheckCircle2 size={18} />
                {success}
              </div>
            )}

            {/* BUTTON */}
            <button
              type="submit"
              disabled={saving}
              className="bg-gradient-to-r from-[#8B5E12] via-[#B67D22] to-[#D4A437] hover:opacity-95 transition-all text-white font-semibold rounded-2xl px-8 py-3 flex items-center gap-2 shadow-lg"
            >
              {saving ? (
                <Loader2
                  size={18}
                  className="animate-spin"
                />
              ) : (
                <Save size={18} />
              )}

              {saving
                ? editingEnquiry
                  ? 'Updating Enquiry...'
                  : 'Saving Enquiry...'
                : editingEnquiry
                  ? 'Update Enquiry'
                  : 'Save Enquiry'}
            </button>
          </div>

          {/* RIGHT PANEL */}
          <div className="space-y-5 xl:max-w-[340px]">

            {/* SUMMARY */}
            <div className="bg-[#FFF8E8] border border-[#E4C77F] rounded-2xl p-4 shadow-sm">
              <h3 className="font-bold text-base text-[#8B5E12] mb-3">
                Enquiry Summary
              </h3>

              <SummaryItem
                label="Customer"
                value={`${form.salutation} ${form.name}`.trim()}
              />

              <SummaryItem
                label="Mobile"
                value={form.mobile}
              />

              <SummaryItem
                label="Enquiry Type"
                value={form.enquiry_type}
              />

              <SummaryItem
                label="Ornament Type"
                value={form.ornament_type}
              />

              <SummaryItem
                label="Processing Fee (₹)"
                value={form.processing_fee}
              />

              <SummaryItem
                label="Gross Weight"
                value={form.gross_weight_gms}
              />

              <SummaryItem
                label="Net Weight"
                value={form.net_weight_gms}
              />

              <SummaryItem
                label="Rate"
                value={form.rate}
              />

              <SummaryItem
                label={
                  form.enquiry_type ===
                  'Pledge Gold'
                    ? 'Expected Rate'
                    : 'Gross Amount'
                }
                value={grossAmount}
              />

              <SummaryItem
                label="Net Amount"
                value={netAmount}
              />

              {form.enquiry_type === 'Pledge Gold' && (
                <>
                  <SummaryItem
                    label="Pledge Amount"
                    value={form.pledge_amount}
                  />
                  <SummaryItem
                    label="Financier Name"
                    value={form.financier_name}
                  />
                  <SummaryItem
                    label="Financier Branch"
                    value={form.financier_branch}
                  />
                </>
              )}

              <SummaryItem
                label="Lead State"
                value={form.lead_state}
              />

              <SummaryItem
                label="Lead Status"
                value={form.lead_status}
              />

              <SummaryItem
                label="Lead Stage"
                value={form.lead_stage}
              />

              <SummaryItem
                label="Priority"
                value={form.priority}
              />
            </div>

            {/* RECENT */}
            <div className="bg-white border border-[#E5D2A0] rounded-2xl p-4 shadow-sm">
              <h3 className="font-bold text-gray-800 mb-4">
                Recent Enquiries
              </h3>

              {loadingRecent ? (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Loader2
                    size={16}
                    className="animate-spin"
                  />
                  Loading...
                </div>
              ) : recentEnquiries.length > 0 ? (
                <div className="space-y-3">
                  {recentEnquiries.map(
                    (item) => (
                      <div
                        key={item.enquiry_id}
                        className="border border-[#E8D5A8] rounded-xl p-3 bg-[#FFFDF8]"
                      >
                        <div className="flex items-center justify-between">
                          <p className="font-semibold text-gray-800">
                            {
                              item.enquiry_type
                            }
                          </p>

                          <span className="text-xs text-[#A9741F] font-medium">
                            ID #
                            {
                              item.enquiry_id
                            }
                          </span>
                        </div>

                        <p className="text-sm text-gray-500 mt-1">
                          {item.created_at}
                        </p>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  No recent enquiries found
                </p>
              )}
            </div>

          </div>
                  </div>
                </form>
                </div>
              </div>
          )}
        </div>
      </div>
    </div>
  )
}

function InputField({
  label,
  value,
  onChange,
  type = 'text',
  readOnly = false,
  maxLength
}) {
  return (
    <div>
      <label className="text-sm font-medium text-gray-700">
        {label}
      </label>

<input
  type={type}
  value={value}
  readOnly={readOnly}
  maxLength={maxLength}
  inputMode={
    type === 'tel'
      ? 'numeric'
      : undefined
  }
  pattern={
    type === 'tel'
      ? '[0-9]*'
      : undefined
  }
  onChange={(e) =>
    !readOnly &&
    onChange(e.target.value)
  }
  className={`mt-1 w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 outline-none focus:border-[#B67D22] ${
    readOnly
      ? 'bg-gray-100 text-gray-700 cursor-not-allowed'
      : ''
  }`}
/>
    </div>
  )
}

function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (ref.current && !ref.current.contains(event.target)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const displayValue = value || placeholder || 'Select'

  return (
    <div className="relative" ref={ref}>
      <label className="text-sm font-medium text-gray-700">
        {label}
      </label>

      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="mt-1 w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 text-left outline-none focus:border-[#B67D22] flex items-center justify-between"
      >
        <span>{displayValue}</span>
        <span className="text-gray-400">▾</span>
      </button>

      {open && (
        <div className="absolute z-30 mt-2 w-full max-h-60 overflow-y-auto rounded-2xl border border-[#D8C08A] bg-white shadow-xl">
          {options.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                onChange(option)
                setOpen(false)
              }}
              className="w-full text-left px-4 py-3 hover:bg-amber-50 focus:bg-amber-50"
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryItem({
  label,
  value
}) {
  return (
    <div className="mb-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">
        {label}
      </p>

      <p className="text-gray-900 font-semibold mt-1">
        {value || '—'}
      </p>
    </div>
  )
}

function formatDateTime(value) {
  if (!value) return '—'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString('en-IN', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
