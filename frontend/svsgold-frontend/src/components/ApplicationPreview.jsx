import React, { useState, useEffect, useRef } from 'react'
import { ChevronLeft, Loader, AlertCircle, Download, Printer } from 'lucide-react'
import { accountsAPI, applicationsAPI } from '../api/api'
import { formatDate } from '../utils/validation'
import PdfGenerator from '../utils/PdfGenerator'
import { useNavigate } from 'react-router-dom'

export default function ApplicationPreview({ application, userIdentifier, onBack, initialData = null }) {
  const navigate = useNavigate()
  const printRef = useRef(null)
  const initialAccount = initialData?.account || initialData?.customer || {}
  const initialAddressesPresent = Array.isArray(initialData?.addresses) && initialData.addresses.length > 0
  const hasCompleteInitialData = !!(
    initialData &&
    (initialAccount.name || initialAccount.first_name || initialAccount.email || initialAccount.mobile) &&
    Array.isArray(initialData.addresses)
  )
  const [previewData, setPreviewData] = useState(hasCompleteInitialData && initialAddressesPresent ? initialData : null)
  const [loading, setLoading] = useState(!(hasCompleteInitialData && initialAddressesPresent))
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [branchInfo, setBranchInfo] = useState(null)

  useEffect(() => {
    let active = true

    const loadPreview = async () => {
      try {
        if (!(hasCompleteInitialData && initialAddressesPresent)) {
          setPreviewData(null)
        }
        setLoading(true)
        setError('')

        let preview = (hasCompleteInitialData && initialAddressesPresent) ? initialData : null
        let appObj = application || {}

        if (!preview) {
          const appId = application?.application_id || application?.application?.application_id
          if (!appId) {
            throw new Error('Application id missing for preview')
          }

          const contextRes = await applicationsAPI.getApplicationPreview(userIdentifier, appId)
          const d = contextRes?.data || {}
          const appPledge = d.pledge_details || {}
          const appOrnaments = d.ornaments || []
          appObj = d.application || application || {}

          preview = {
            account: d.customer || {},
            addresses: d.addresses || [],
            documents: d.documents || [],
            bank_account: null,
            pledge_details: appPledge || {},
            ornaments: appOrnaments,
            application: { ...appObj, ...(application || {}) }
          }
        } else if (application) {
          preview = {
            ...preview,
            application: { ...(preview.application || {}), ...application }
          }
          appObj = preview.application
        }

        if (!active) {
          return
        }

        setPreviewData(preview)

        // Fetch branch info using place from search API application
        try {
          const br = await applicationsAPI.getBranches()
          if (!active) {
            return
          }
          const branches = br.data?.branches || []
          const place = (appObj?.place || application?.place || '').toLowerCase().trim()
          if (place) {
            let matched = branches.find(b => b.branch_name.toLowerCase() === place)
            if (!matched) matched = branches.find(b => b.branch_name.toLowerCase().includes(place) || place.includes(b.branch_name.toLowerCase()))
            if (matched) setBranchInfo(matched)
          }
        } catch {}
      } catch (err) {
        if (active) {
          console.log('Preview load error:', err)
          setError('Failed to load preview data.')
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadPreview()

    return () => {
      active = false
    }
  }, [application?.application_id, application?.place, application?.application_type, hasCompleteInitialData, initialData, userIdentifier])


  const handleDownloadPdf = async () => {
    if (!previewData) return
    try {
      setDownloading(true)
      const g = new PdfGenerator()
      const t = application?.application_type || previewData.application?.application_type || ''
      const b = t === 'PLEDGE_RELEASE' ? await g.generatePledgeReleasePdf(previewData) : await g.generateDirectBuyingPdf(previewData)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([b], { type: 'application/pdf' }))
      a.download = `${previewData.application?.application_no || 'application'}.pdf`
      a.click(); URL.revokeObjectURL(a.href)
    } catch { setError('Failed to generate PDF.') }
    finally { setDownloading(false) }
  }

  const handlePrint = () => {
    const h = printRef.current?.innerHTML; if (!h) return
    const w = window.open('', '_blank')
    w.document.write(`<html><head><meta charset="utf-8"><title>Application</title><style>*{margin:0;padding:0;box-sizing:border-box}html,body{background:#fff!important;color:#000!important;font-family:'Times New Roman',serif}body{padding:0;margin:0}@media print{.no-print{display:none!important}html,body{background:#fff!important;color:#000!important}body{margin:0;padding:0}@page{size:A4;margin:8mm 10mm;widows:3;orphans:3}[style*="pageBreakBefore"]{page-break-before:always}}</style></head><body>${h}</body></html>`)
    w.document.close(); setTimeout(() => { w.print(); w.close() }, 400)
  }

  /* ---- Data extraction ---- */
  const app = previewData?.application || {}
  const rawAccount = previewData?.account || previewData?.customer || {}
  const acc = rawAccount || {}
  const addrs = previewData?.addresses || []
  const pledge = previewData?.pledge_details || {}
  const ornaments = previewData?.ornaments || []
  const docs = previewData?.documents || []
  const appType = application?.application_type || app.application_type || ''
  const isPR = appType === 'PLEDGE_RELEASE'

  const name = acc.name || [acc.first_name, acc.last_name].filter(Boolean).join(' ') || pledge.pledger_name || ''
  const email = acc.email || acc.email_id || ''
  const dob = acc.date_of_birth || acc.dob || ''
  const gender = acc.gender || ''
  const occupation = acc.occupation || ''
  const maritalStatus = acc.marital_status || acc.marriage_status || ''
  const aadharNo = acc.aadhar_no != null ? String(acc.aadhar_no) : (acc.aadhaar_no != null ? String(acc.aadhaar_no) : '')
  const panNo = acc.pan_no != null ? String(acc.pan_no) : ''
  const accountAddressFallback = acc.address_text || [acc.address_line, acc.street, acc.city, acc.district, acc.state, acc.pincode, acc.country].filter(Boolean).join(', ')

  const normalizeAddress = (addr) => {
    if (!addr || typeof addr !== 'object') return null
    return {
      ...addr,
      address_type: addr.address_type || addr.type || '',
      address_text: addr.address_text || addr.full_address || addr.address || '',
      address_line: addr.address_line || addr.line1 || addr.line || ''
    }
  }

  const normalizedAddresses = addrs.map(normalizeAddress).filter(Boolean)
  const findAddress = (pattern) => normalizedAddresses.find(a => pattern.test(`${a.address_type || ''} ${a.address_text || ''}`))
  const present = findAddress(/present|current|residential/i) || normalizedAddresses[0] || app.present_address || app.address_text || acc.address_text || null
  const perm = findAddress(/permanent/i) || normalizedAddresses[1] || app.permanent_address || app.address_text || acc.address_text || present

  const formatAddress = (a) => {
    if (typeof a === 'string') return a
    if (!a) return accountAddressFallback || pledge.pledger_address || ''
    const parts = []
    if (a.address_text) {
      parts.push(a.address_text)
    } else {
      parts.push(
        a.address_line,
        a.street,
        a.city,
        a.district,
        a.state,
        a.pincode,
        a.country
      )
    }
    const formatted = parts.filter(Boolean).join(', ')
    return formatted || accountAddressFallback || pledge.pledger_address || ''
  }
  const fA = formatAddress
  const age = (d) => { if (!d) return ''; const b = new Date(d), t = new Date(); let a = t.getFullYear() - b.getFullYear(); if (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate())) a--; return a }
  const cur = (n) => (!n && n !== 0) ? '' : Number(n).toLocaleString('en-IN')

  // Find photo from documents or account
  const photoDoc = docs.find(d => /photo/i.test(d.document_type))
  const photoUrl = acc.photo_url || photoDoc?.file_path || ''

  let tQ = 0, tW = 0
  ornaments.forEach(o => { tQ += Number(o.quantity) || 0; tW += Number(o.approx_weight_gms) || 0 })

  const blue = '#2c5f8a'
  const cb = '1px solid #6a9ec7'
  const hBg = 'linear-gradient(180deg, #3a7ab5, #2c5f8a)'
  const lbl = { border: cb, padding: '4px 8px', fontWeight: 'bold', background: '#f0f6fb', fontSize: '10px' }
  const val = { border: cb, padding: '4px 8px', fontSize: '10px' }

  if (loading) return (
    <div className="flex items-center justify-center h-96"><div className="text-center">
      <Loader size={48} className="animate-spin mx-auto mb-4" style={{ color: '#a36e24' }} /><p className="text-gray-600">Loading Preview...</p>
    </div></div>
  )

  return (
    <div className="space-y-6">
      {/* Action bar */}
      <div className="flex items-center justify-between no-print">
        <button onClick={onBack} className="flex items-center gap-2 px-4 py-2 text-amber-700 hover:bg-amber-50 rounded-xl font-medium transition-colors"><ChevronLeft size={20} /> Back to Applications</button>
      </div>

      {error && <div className="flex items-start gap-3 p-4 bg-red-50 border-2 border-red-200 rounded-xl"><AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} /><span className="text-sm text-red-700">{error}</span></div>}

      {/* ================================================================ */}
      {/*  PAGE 1: APPLICATION FORM                                       */}
      {/* ================================================================ */}
      <div ref={printRef}>
        <div style={{ fontFamily: "'Times New Roman',Georgia,serif", maxWidth: '720px', margin: '0 auto', background: '#fff', border: '1px solid #ddd', borderRadius: '4px', overflow: 'hidden' }}>

          {/* HEADER */}
          <div style={{ background: hBg, padding: '12px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ color: '#fff', lineHeight: '1.3', fontSize: '9.5px' }}>
              <div style={{ fontSize: '14px', fontWeight: 'bold' }}>SVS GOLD</div>
              <div style={{ fontSize: '8px', opacity: .85 }}>{branchInfo?.full_address_txt}</div>
              <div style={{ fontSize: '8px', opacity: .85 }}>{branchInfo?.phone_number}</div>
            </div>
            <div style={{ textAlign: 'center', color: '#fff' }}>
              <div style={{ fontSize: '18px', fontWeight: 'bold', letterSpacing: '1px' }}>APPLICATION</div>
            </div>
            <div style={{ width: '70px', height: '50px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img src={import.meta.env.BASE_URL + 'svslogo-white.png'} alt="SVS Gold" style={{ maxHeight: '48px', maxWidth: '65px', objectFit: 'contain' }} />
            </div>
          </div>

          <div style={{ padding: '14px 20px' }}>

            {/* CUSTOMER DETAILS with Photo */}
            <div style={{ fontSize: '12px', fontWeight: 'bold', color: blue, marginBottom: '6px' }}>CUSTOMER DETAILS</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '10px' }}>
              <tbody>
                <tr>
                  <td style={lbl} width="120">Application No.</td>
                  <td style={val} colSpan={5}>{app.application_no || ''}</td>
                  {/* Photo cell spanning multiple rows */}
                  <td style={{ border: cb, padding: '2px', textAlign: 'center', verticalAlign: 'top', width: '75px' }} rowSpan={8}>
                    {photoUrl ? (
                      <img src={photoUrl} alt="Customer" style={{ width: '70px', height: '80px', objectFit: 'cover', borderRadius: '2px' }} />
                    ) : (
                      <div style={{ width: '70px', height: '80px', background: '#f0f6fb', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px', color: '#999', border: '1px dashed #bbb', margin: '0 auto' }}>Photo</div>
                    )}
                  </td>
                </tr>
                <tr>
                  <td style={lbl}>Name</td>
                  <td style={val} colSpan={5}>{name}</td>
                </tr>
                <tr>
                  <td style={lbl}>Email ID</td>
                  <td style={val}>{email}</td>
                  <td style={{ ...lbl, width: '60px' }}>D.O.B.</td>
                  <td style={val}>{dob}</td>
                  <td style={{ ...lbl, width: '40px' }}>Age</td>
                  <td style={{ ...val, width: '40px' }}>{age(dob)}</td>
                </tr>
                <tr>
                  <td style={lbl}>Mobile No.</td>
                  <td style={val}>{app.mobile || acc.mobile || userIdentifier || ''}</td>
                  <td style={lbl}>Aadhar No.</td>
                  <td style={val}>{aadharNo}</td>
                  <td style={lbl}>PAN No.</td>
                  <td style={val}>{panNo}</td>
                </tr>
                <tr>
                  <td style={lbl}>Present Address</td>
                  <td style={val} colSpan={5}>{fA(present)}</td>
                </tr>
                <tr>
                  <td style={lbl}>Permanent Address</td>
                  <td style={val} colSpan={5}>{fA(perm)}</td>
                </tr>
                <tr>
                  <td style={lbl}>Occupation</td>
                  <td style={val}>{occupation}</td>
                  <td style={lbl}>Gender</td>
                  <td style={val}>{gender}</td>
                  <td style={lbl}>Marital Status</td>
                  <td style={val}>{maritalStatus}</td>
                </tr>
              </tbody>
            </table>

            {/* DECLARATION / RELEASE FORM */}
            {!isPR ? (
              <>
                <div style={{ fontSize: '12px', fontWeight: 'bold', textAlign: 'center', color: blue, marginBottom: '6px', textDecoration: 'underline' }}>OWNERSHIP DECLARATION</div>
                <div style={{ fontSize: '9.5px', lineHeight: '1.6', textAlign: 'justify', marginBottom: '12px' }}>
                  I <strong style={{ borderBottom: '1px solid #333', padding: '0 4px' }}>{name || '____________'}</strong> hereby declare on the oath that the gold items described below belongs to me, and I am the sole owner of the gold items which I offered to sell to <strong>SVS Gold Private Limited (' SVS Gold')</strong>. I confirm that I have acquired these properties legally and declare that I have clear, absolute transferable, and saleable rights on the articles offered to sell. I propose to sell the under-mentioned items to SVS Gold and confirm that all the information provided here are true and correct. I have thoroughly read and understood the Terms & Conditions mentioned along with the application form. I further state that I shall be legally held responsible to any Government Authority. If the gold items sold by me found to be stolen property, then SVS Gold shall have no liability or responsibility towards the payment of value of the same to me and can handover it to the Authorities, if required.
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: '12px', fontWeight: 'bold', textAlign: 'center', color: blue, marginBottom: '6px', textDecoration: 'underline' }}>GOLD RELEASE FORM</div>
                <div style={{ fontSize: '9.5px', lineHeight: '1.6', textAlign: 'justify', marginBottom: '12px' }}>
                  I am <strong>{pledge.pledger_name || '______'}</strong> having gold ornaments pledged with <strong>{pledge.financier_name || '______'}</strong>, <strong>{pledge.branch_name || '______'}</strong> branch (the financier company), but my financial situation prevents me from releasing them. I have decided to sell these gold ornaments to <strong>SVS Gold Private Limited (' SVS Gold')</strong> and I am authorizing their representative, Mr. <strong>{pledge.authorized_person || '______'}</strong>, to release the ornaments on my behalf by settling the total dues of Rs. <strong>{cur(pledge.total_due) || '______'}</strong>, including Rs. <strong>{cur(pledge.principal_amount) || '______'}</strong> as principal and Rs. <strong>{cur(pledge.interest_amount) || '______'}</strong> as an interest to the financier / customer account directly. I have the original pawn ticket/loan documents for release. Once SVS Gold has possession of the gold ornaments, any remaining balance should be settled to me based on the rate declared by SVS Gold, minus their 5% margin on the market value of the gold ornaments. The documents submitted by me subsequently, if found to be incorrect or sham /not genuine in such event I shall be held liable to the financier company and SVS Gold. Also, I shall be solely responsible for any legal action. I hereby submit cheque No. <strong>{pledge.cheque_no || '______'}</strong> dated <strong>{pledge.cheque_date || '______'}</strong> against receipt of advance as a security deposit.
                </div>
              </>
            )}

            {/* ORNAMENTS TABLE - PAGE 1 */}
            <div style={{ fontSize: '10px', textAlign: 'center', fontWeight: 'bold', marginBottom: '5px', marginTop: '8px', color: blue }}>List of the ornaments offered for sale to SVS GOLD</div>
            {isPR && (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '9.5px', marginBottom: '4px' }}>
                <tbody>
                  <tr><td style={lbl} width="180">Pledger Name and Address</td><td style={val}>{[pledge.pledger_name, pledge.pledger_address || fA(present)].filter(Boolean).join(', ')}</td></tr>
                  <tr><td style={lbl}>Gold Loan Account No</td><td style={val}>{pledge.gold_loan_account_no || ''}</td></tr>
                </tbody>
              </table>
            )}
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '9.5px', marginBottom: '8px' }}>
              <thead>
                <tr style={{ background: '#f0f6fb' }}>
                  <th style={{ border: cb, padding: '4px 4px', textAlign: 'center', fontWeight: 'bold', width: '35px' }}>S.No</th>
                  <th style={{ border: cb, padding: '4px 4px', textAlign: 'left', fontWeight: 'bold' }}>Item Name</th>
                  <th style={{ border: cb, padding: '4px 4px', textAlign: 'center', fontWeight: 'bold', width: '55px' }}>Qty</th>
                  {isPR && <th style={{ border: cb, padding: '4px 4px', textAlign: 'center', fontWeight: 'bold', width: '70px' }}>Purity</th>}
                  <th style={{ border: cb, padding: '4px 4px', textAlign: 'center', fontWeight: 'bold', width: '80px' }}>Weight (GMS)</th>
                </tr>
              </thead>
              <tbody>
                {ornaments.map((o, i) => (
                  <tr key={i}>
                    <td style={{ ...val, textAlign: 'center' }}>{i + 1}</td>
                    <td style={val}>{o.item_name || ''}</td>
                    <td style={{ ...val, textAlign: 'center' }}>{o.quantity || ''}</td>
                    {isPR && <td style={{ ...val, textAlign: 'center' }}>{o.purity_percentage || ''}</td>}
                    <td style={{ ...val, textAlign: 'center' }}>{o.approx_weight_gms || ''}</td>
                  </tr>
                ))}
                {Array.from({ length: Math.max(2, 2 - ornaments.length) }).map((_, i) => (
                  <tr key={`e${i}`}>
                    <td style={{ ...val, height: '18px' }}>&nbsp;</td>
                    <td style={val}>&nbsp;</td>
                    <td style={val}>&nbsp;</td>
                    {isPR && <td style={val}>&nbsp;</td>}
                    <td style={val}>&nbsp;</td>
                  </tr>
                ))}
                <tr style={{ background: '#f0f6fb' }}>
                  <td style={{ ...lbl, textAlign: 'left' }} colSpan={2}>Total No. of Quantity</td>
                  <td style={{ ...val, textAlign: 'center', fontWeight: 'bold' }}>{tQ || ''}</td>
                  {isPR && <td style={lbl}>&nbsp;</td>}
                  <td style={{ ...val, textAlign: 'center', fontWeight: 'bold' }}>
                    <div style={{ fontSize: '9px', marginBottom: '2px' }}>Total Approx. weight (Gms)</div>
                    <div style={{ fontWeight: 'bold' }}>{tW ? tW.toFixed(2) : ''}</div>
                  </td>
                </tr>
              </tbody>
            </table>

            <div style={{ fontSize: '9px', lineHeight: '1.5', marginBottom: '8px' }}>
              These weights are approximate only. I confirm that I have read, understood, and agree with the terms & conditions laid down by <strong>SVS Gold</strong>.
            </div>

            {/* DATE / PLACE / SIGNATURE - PAGE 1 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '10px', marginBottom: '6px' }}>
              <table style={{ fontSize: '9.5px', borderCollapse: 'collapse' }}><tbody>
                <tr><td style={lbl}>Date</td><td style={{ ...val, minWidth: '100px' }}>{app.application_date || ''}</td></tr>
                <tr><td style={lbl}>Place</td><td style={val}>{app.place || application?.place || ''}</td></tr>
              </tbody></table>
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '150px', borderBottom: '1px solid #666', paddingBottom: '28px', marginBottom: '2px' }}></div>
                <div style={{ fontSize: '8px', color: '#555' }}>Signature</div>
              </div>
            </div>

          </div>

          {/* ================================================================ */}
          {/*  PAGE 2: TERMS & CONDITIONS                                     */}
          {/* ================================================================ */}
          <div style={{ pageBreakBefore: 'always', borderTop: '3px solid #2c5f8a', padding: '16px 28px' }}>
            <div style={{ fontSize: '12px', fontWeight: 'bold', textAlign: 'center', color: blue, marginBottom: '8px', textDecoration: 'underline' }}>
              Terms and Conditions for Sale of Gold Items
            </div>
            <ol style={{ fontSize: '8.5px', lineHeight: '1.4', paddingLeft: '16px', color: '#1f2937', marginBottom: '10px' }}>
              <li><strong>SVS</strong> Gold will only accept Gold Items exclusively owned by the Seller and acquired through purchase, gift or inheritance.</li>
              <li><strong>SVS</strong> Gold will not return Gold Items once sold. Payment will be made to seller's bank account only.</li>
              <li><strong>SVS</strong> Gold reserves rights to accept or reject any application without explanation.</li>
              <li>Upon purchase, <strong>SVS</strong> Gold acquires absolute right to sell, transfer, or melt the Gold Items.</li>
              <li><strong>SVS</strong> Gold shall not be held responsible if sales proceeds are used for illegal purposes.</li>
              <li>If sold Gold Items are found stolen or spurious, Seller is solely responsible for all consequences and compensation.</li>
              <li><strong>SVS</strong> Gold reserves rights to verify pledge information and share with authorities if false.</li>
              <li>If Seller changes mind about selling after release from pledge, must reimburse advance to financier.</li>
              <li>Failure to reimburse advance before transaction end will be treated as sale to <strong>SVS</strong> Gold.</li>
              <li>If Gold Items value is less than advance paid, Seller must pay the difference immediately.</li>
              <li><strong>SVS</strong> Gold uses XRF technology for purity checking. Readings may vary by methodology.</li>
              <li><strong>SVS</strong> Gold not responsible for weight/purity loss after melting; Seller pays losses.</li>
              <li><strong>SVS</strong> Gold not responsible for item shape/size changes after melting.</li>
              <li><strong>SVS</strong> Gold may use acid, salt, or other tests to confirm purity.</li>
              <li><strong>SVS</strong> Gold deducts non-gold material weight before calculating actual weight.</li>
              <li><strong>SVS</strong> Gold reserves rights to conduct verification to establish ownership credibility.</li>
              <li>Value based on 24-carat gold market price, subject to fluctuations on day of acquisition.</li>
              <li><strong>SVS</strong> Gold takes biometric details for record purposes only (confidential).</li>
              <li>Sellers below 21 must be accompanied by legal guardian; both equally responsible.</li>
              <li><strong>SVS</strong> Gold can charge 5% if Seller changes mind after ornament is dismantled/melted.</li>
            </ol>

            <div style={{ fontSize: '8px', lineHeight: '1.4', marginBottom: '8px', textAlign: 'justify' }}>
              By signing, the Seller agrees to all terms and conditions and sells Gold Items of their free will without coercion or duress, and is satisfied with the valuation and amount offered.
            </div>

            {/* DATE / PLACE / SIGNATURE (Page 2) */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '8px' }}>
              <table style={{ fontSize: '9.5px', borderCollapse: 'collapse' }}><tbody>
                <tr><td style={lbl}>Date</td><td style={{ ...val, minWidth: '80px' }}>{app.application_date || ''}</td></tr>
                <tr><td style={lbl}>Place</td><td style={val}>{app.place || application?.place || ''}</td></tr>
              </tbody></table>
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: '100px', borderBottom: '1px solid #666', paddingBottom: '20px', marginBottom: '2px' }}></div>
                <div style={{ fontSize: '7.5px', color: '#555' }}>Signature</div>
              </div>
            </div>

            {/* FOR OFFICE USE ONLY */}
            <div style={{ borderTop: '1px solid #2c5f8a', paddingTop: '8px' }}>
              <div style={{ fontSize: '11px', fontWeight: 'bold', textAlign: 'center', color: blue, marginBottom: '4px' }}>FOR OFFICE USE ONLY</div>
              <div style={{ fontSize: '8px', lineHeight: '1.3', textAlign: 'justify', marginBottom: '6px' }}>
                I have verified all original documents. Based on customer declaration, I believe the customer is genuine.
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                <table style={{ fontSize: '9px', borderCollapse: 'collapse' }}><tbody>
                  <tr><td style={lbl}>Manager</td><td style={{ ...val, minWidth: '100px' }}></td></tr>
                  <tr><td style={lbl}>Sign</td><td style={val}></td></tr>
                </tbody></table>
                <table style={{ fontSize: '9px', borderCollapse: 'collapse' }}><tbody>
                  <tr><td style={lbl}>Date</td><td style={{ ...val, minWidth: '70px' }}></td></tr>
                  <tr><td style={lbl}>Place</td><td style={val}></td></tr>
                </tbody></table>
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* BOTTOM ACTIONS */}
      {(() => {
        const status = (application?.status || app.status || '').toUpperCase()
        const isSubmitted = ['SUBMITTED','APPROVED','COMPLETED'].includes(status)
        return (
          <>
            <div className="flex justify-center no-print">
              <button onClick={handlePrint} className="px-8 py-3 bg-white hover:bg-gray-50 text-gray-700 font-bold rounded-xl shadow-md flex items-center justify-center gap-2 border border-gray-200 transition-all"><Printer size={20} /> Print Application</button>
            </div>
            {!isSubmitted && (
              <div className="flex justify-center no-print">
                <button onClick={() => navigate('/estimation', { state: { application: previewData } })} className="px-10 py-3 text-white font-semibold rounded-xl shadow-lg flex items-center justify-center gap-2 text-sm transition-all hover:-translate-y-0.5" style={{ background: 'linear-gradient(135deg,#16a34a,#15803d)', boxShadow: '0 4px 14px rgba(22,163,74,0.3)' }}>
                  Accept & Continue to Estimation →
                </button>
              </div>
            )}
          </>
        )
      })()}
    </div>
  )
}
